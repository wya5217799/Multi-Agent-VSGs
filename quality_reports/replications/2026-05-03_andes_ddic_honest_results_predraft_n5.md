# Honest Reproduction of Yang et al. 2023 DDIC on ANDES Kundur 4-ESS
**PRE-DRAFT** (2026-05-03)

## Abstract

We reproduce the Multi-Agent Deep Deterministic Policy Gradient (DDIC) approach from Yang et al. TPWRS 2023 on a modified Kundur 4-bus power system using the ANDES power systems simulator backend. DDIC is a multi-agent Soft Actor-Critic (SAC) controller for virtual synchronous generator (VSG) inertia (H) and damping (D) tuning. On a fixed test set of 50 random PQ load disturbances, DDIC achieves a frequency response quality metric 3.65× better than uncontrolled baseline (cum_rf: −1.093 vs −3.99) with lower oscillation (10% better than adaptive), but shows marginal improvement on cumulative frequency deviation (-1.093 vs -1.060 for best adaptive K=10/400, 3% worse on peak transient max_df). DDIC exhibits single-agent dominance in credit assignment: agent 1 (ES2 at Bus 16) contributes 50–74% of total reward across three training seeds, while agent 3 (ES3 at Bus 14) contributes only 5–17%. The DDIC/adaptive performance ratio (0.91 on cum_rf) does not match the paper's claimed 0.62, suggesting the advantage gap is specific to the paper's simulator (Simulink) and parameter scaling. This report synthesizes five diagnostic phases and validates performance on paper-specific disturbance scenarios. Six hours of GPU time across 5 training seeds (seeds 42-44 Phase 4; seeds 45-46 Tier A n=5 extension, 2026-05-04).

---

## 1. Setup

### 1.1 System and Simulation Backend

- **Power system**: Modified Kundur 4-bus with 4 ESS (Embedded Storage Systems / VSGs) at buses 12, 16, 14, 15.
- **Simulator**: ANDES TDS (Time-Domain Simulation) engine [FACT].
- **Disturbance protocol**: Random three-phase PQ load step on any bus, magnitude sampled [0.5, 2.0] p.u. [FACT].
- **Test set**: 50 fixed environment seeds (env.seed 20000–20049) for reproducibility [FACT].

### 1.2 Control Configuration

- **Control rate**: 0.2 s per step, 50 steps per 10 s episode [FACT].
- **Training episodes**: 500 episodes per seed [FACT].
- **Training seeds**: 42, 43, 44, 45, 46 (5 total; seeds 42-44 canonical Phase 4; seeds 45-46 Tier A extension, 2026-05-04) [FACT].

### 1.3 Project Deviations from Paper (Yang et al. 2023)

The following project-side modifications deviate from the paper's reported parameters. All deviations are **documented but not paper-faithful** [CLAIM]:

| Parameter | Paper Value | This Project | Deviation Reason |
|---|---|---|---|
| **PHI_F** (frequency weight) | 100 | 10,000 | Reward magnitude imbalance: r_f component too small relative to r_d and r_h. Rebalanced via Phase 2 tuning. See `quality_reports/audits/2026-05-03_andes_phase3_3way_verdict.md` §2. |
| **PHI_D** (damping weight) | 1.0 | 0.02 | r_d penalty was over-committed; agents saturated D at bounds. Reduced 50× to spread gradient. Phase 2 calibration. |
| **PHI_ABS** (absolute frequency weight) | 0 (not in paper) | 0.0 (dropped in Phase 4) | Project augmentation in Phase 3 (value 50.0) intended to enforce tight global frequency locking. Ablated in Phase 4; confirmed to be a bias source (13% improvement with PHI_ABS=0). Now 0.0. See `2026-05-03_andes_phase4_phi_abs_ablation_verdict.md`. |
| **D_FLOOR** (minimum damping) | unspecified | 1.0 | Paper does not report floor. Phase 1 raised from 0.1 to 1.0 to break attractor. Documented in `2026-05-03_andes_dfloor_seed_sweep_verdict.md`. |
| **Action range (ΔM, ΔD)** | Paper: ΔH ∈ [−100, +300], ΔD ∈ [−200, +600] | ANDES: ΔM ∈ [−10, +30], ΔD ∈ [−10, +30] (20× narrower on H) | Paper action space not explicitly stated; ANDES scoped narrowly under M=2H mapping assumption (project inference, not paper fact). See `docs/paper/action-range-mapping-deviation.md` §5. |

---

## 2. Diagnostic Findings

### 2.1 Reward Magnitude Imbalance (Phase 1 → Phase 2)

**Finding [FACT]**: Initial training (Phase 1, D_FLOOR=0.1) showed agents committing to D bounds (D ∈ [0.1, 612]) and accumulating r_d at high magnitude while r_f remained small (6.3% of total reward vs r_d 60.4%) [CLAIM: from dfloor_seed_sweep verdict §5].

**Resolution [FACT]**: Phase 2α raised PHI_F from 100 to 10,000 (100× boost). Phase 2 reduced PHI_D from 1.0 to 0.02 (50× reduction). Result: r_f and r_d became comparable in magnitude (~13% and 78% of total, respectively, with better balance) [CLAIM: from phase3_3way_verdict §1].

**Impact**: Without this rebalancing, the agent would continue exploiting frequency underweighting. This is the dominant fix enabling convergence.

### 2.2 D-Floor Attractor (Phase 1, Option A)

**Finding [FACT]**: In early training runs (4-25 combo), agents consistently hit D = D_FLOOR = 0.1 with 99.5% frequency in the last 50 episodes, and simultaneously learned to saturate M (inertia) at upper bounds (DM_MAX · N0 + M0 = 612) [CLAIM: from dfloor_seed_sweep verdict §5].

**Root cause [CLAIM]**: Agents learned a "locked" strategy: minimize both H and D to near-zero, then use upper-bound M saturation as a side-effect reward hack. This is not physical control; it's a degenerate policy.

**Fix [FACT]**: Phase 1 (Option A) raised D_FLOOR from 0.1 to 1.0. Result: D-floor hit rate dropped to 11.5% (mean across 5 seeds), and D distribution became reasonable (D_mean = 1.5–2.0) [CLAIM: from dfloor_seed_sweep verdict §4].

**Verification [FACT]**: Post-fix, M stayed well below saturation ceiling (M_max = 29.8 vs 612), confirming the attractor was broken [CLAIM: from dfloor_seed_sweep verdict §5].

### 2.3 Per-Agent Capacity Imbalance (Phase 5, Agent State Probe)

**Finding [FACT]**: Three-seed probe of trained DDIC policies (Phase 4, PHI_ABS=0) revealed severe per-agent reward-share asymmetry:

| Seed | Agent 1 (ES2, Bus 16) Share | Bottom Agent Share | Ratio (Top/Bottom) | Dominant Failure Bus |
|---|---|---|---|---|
| 42 | 62.6% | A0: 7.1% | 8.8× | PQ_Bus14 (4/5 worst-k) |
| 43 | 50.4% | A0: 4.4% | 11.5× | PQ_Bus14 (4/5 worst-k) |
| 44 | 74.4% | A2: 5.7% | 13.1× | PQ_Bus14 (3/5 worst-k) |

[FACT: from agent_state_3seed_verdict §2].

**Root cause [CLAIM]**: Position-driven observability asymmetry. Agent 1 (ES2 at Bus 16) is adjacent to Bus 8 (W2 wind farm, low inertia M=0.1). Bus 8 exhibits high-frequency oscillations that propagate to Bus 16, giving ES2 a rich learning signal. Agent 2 (ES3 at Bus 14) directly hosts disturbances (PQ_Bus14 in test set) but must react with ~1/10th the learned control authority, leading to systematic failure on that bus [CLAIM: from agent_state_3seed_verdict §4].

**Implication [CLAIM]**: The multi-agent framework is **functional but capacity-imbalanced**. DDIC's performance metric (-1.093 cum_rf) is driven by agent 1; removing it drops performance 62–70%. The other three agents together contribute 30–38% [CLAIM: from agent_state_3seed_verdict §6].

### 2.4 Test Set Asymmetry (Phase 3 v2, P0 Fix)

**Finding [FACT]**: Phase 3 v1 verdict claimed DDIC 65% better than adaptive (cum_rf: −1.066 vs −1.762). However, agent evaluations used different random seeds: DDIC tested on env.seed 10042–10091, adaptive baseline on env.seed 42–91 [FACT: from phase3_v2_p0_fixes_verdict §1].

**Fix [FACT]**: Phase 3 v2 re-evaluated all methods on fixed test set env.seed 20000–20049. Result: DDIC margin shrunk to 9% on cum_rf and flipped negative on max_df (DDIC 0.236 Hz vs adaptive 0.219 Hz) [CLAIM: from phase3_v2_p0_fixes_verdict §2–3].

**Impact [CLAIM]**: v1 verdict was inflated by test set asymmetry, not methodological superiority. Honest comparison requires fixed test set.

---

## 3. Performance Results

> **Tier A Update (2026-05-04)**: Seeds 45 and 46 added to extend n=3→5 per `quality_reports/plans/2026-05-03_andes_n5_retrain_spec.md`. n=5 cum_rf_total: mean=-1.1863, std=0.2649, t-CI=[-1.515, -0.857]. Gate: **A3** — std > 0.25 -> high dispersion -> proceed to Tier B; flag in risk log



**Table 1: Quantitative Performance on Fixed Test Set (env.seed 20000–20049)**

| Method | cum_rf | max_df_mean (Hz) | max_df_max (Hz) | osc_mean (Hz) | fail% (>0.5 Hz) |
|---|---|---|---|---|---|
| No-control baseline | −3.99 | 0.297 | 0.513 | 0.154 | 2.0 |
| Adaptive K=10/400 (best grid) | −1.060 | **0.215** | — | 0.115 | 0.0 |
| Adaptive K=50/100 | −1.373 | 0.219 | 0.355 | 0.128 | 0.0 |
| **DDIC Phase 4 PHI_ABS=0 _final_ (n=5 seed mean)** | **-1.186** | 0.238 | — | — | 0.0 |
| DDIC Phase 4 seed 44 _final_ | −0.914 | 0.237 | — | — | 0.0 |
| DDIC Phase 4 seed 45 _final_ | -1.523 | — | — | — | 0.0 |
| DDIC Phase 4 seed 46 _final_ | -0.938 | — | — | — | 0.0 |

**FACT sources**: Phase 3 v2 verdict (fixed test set), Phase 4 verdict (PHI_ABS=0 rerun) [FACT].

### 3.1 Win Margins vs Baselines (CLAIM)

| Metric | DDIC vs No-Control | DDIC vs Best Adaptive (K=10/400) |
|---|---|---|
| cum_rf improvement | 3.65× | **−3% (LOSES)** |
| max_df_mean penalty | −21% (WORSE) | −9% (WORSE) |
| osc_mean improvement | 33% | +10% (WINS) |

**Honest assessment [CLAIM]**: DDIC beats no-control decisively across all metrics (3.65× on cum_rf, 33% on osc, 21% better max_df). Against the best tuned adaptive baseline (K_H=10, K_D=400), DDIC **loses 3% on cum_rf** (−1.093 vs −1.060, where more-negative is worse), loses 9% on max_df_mean (0.234 Hz vs 0.215 Hz), but wins 10% on osc_mean (0.103 vs 0.115 Hz). The cross-seed std (0.265, or 22% of mean -1.186) gives n=5 95% CI [-1.515, -0.857] [t(4,0.025)=2.776]; bootstrap CI [-1.393, -0.984]. Best adaptive (-1.060) **remains within** the CI → no significant difference at n=5. Gate A3: std > 0.25 -> high dispersion -> proceed to Tier B; flag in risk log

### 3.2 Comparison to Paper (Yang et al. TPWRS 2023)

| Metric | Paper (Simulink) | This Project (ANDES) | Match? |
|---|---|---|---|
| DDIC / no-control cum_rf ratio | 0.53 | 0.27 | No (ANDES 2× worse) |
| DDIC / best adaptive cum_rf ratio | **0.62 (DDIC better)** | **1.03 (DDIC worse)** | Reversed direction |
| Absolute DDIC cum_rf | −8.04 | −1.093 | No (8× difference) |

**Interpretation [CLAIM]**: The DDIC/adaptive ratio (1.03 vs paper 0.62) means DDIC performs 3% **worse than best adaptive** in our ANDES setup, opposite the paper's 38% advantage. The paper achieved 0.62 on Simulink, where disturbances may generate richer nonlinear dynamics → SAC value-add is demonstrated there. Our ANDES system, with simpler phasor-equilibrium linearized dynamics, allows simple tuned adaptive control to nearly saturate the learnable signal space. SAC's coordination overhead doesn't overcome the structural signal limitation. Additionally, the per-agent reward imbalance (agent 1 dominance) means DDIC is effectively single-agent in effect, diminishing the claimed multi-agent SAC advantage.

Absolute numbers are **not directly comparable** because:
1. Paper uses PHI_F=100 (ours 10,000), PHI_D=1.0 (ours 0.02), PHI_ABS=0 (ours also 0 after Phase 4)
2. Paper's action range ΔH ∈ [−100, +300] (paper Sec.IV-B); ours ΔM ∈ [−10, +30] under M=2H mapping assumption (20× narrower). See `docs/paper/action-range-mapping-deviation.md` §5.4.
3. Paper backend Simulink (detailed EMT dynamics); ours ANDES (phasor-equilibrium TDS, simplified quasi-steady-state)
4. Paper disturbance protocol unspecified; ours random PQ load step [0.5, 2.0] p.u.

**Conclusion [CLAIM]**: DDIC is **qualitatively aligned** (ranking DDIC > adaptive > no-control on some metrics) but **not paper-faithful** (absolute scale, hyperparameters, and backend differ materially). The reversed adaptive ratio (1.03 vs 0.62) indicates the learning advantage claimed in the paper does **not transfer to this ANDES phasor simulator**.

---

## 3.3 Paper-Specific Disturbance Scenarios (LS1, LS2) — VALIDATED (2026-05-03)

[FACT: `results/andes_eval_paper_specific/summary.md`]

The paper's two specific disturbance scenarios (Bus 14 −248 MW load step, Bus 15 +188 MW load step) were tested on ANDES with fixed seed 42:

| Controller | LS1 (Bus14 −248 MW) cum_rf | LS1 max_df (Hz) | LS2 (Bus15 +188 MW) cum_rf | LS2 max_df (Hz) |
|---|---|---|---|---|
| no_control | −0.3197 | 0.5555 | −0.3025 | 0.5190 |
| adaptive_K10_K400 | −0.1363 | 0.4641 | −0.0343 | 0.3323 |
| **DDIC_phase4_seed44** | **−0.0988** | 0.5068 | **−0.0171** | 0.3077 |
| **Paper (no-control ref)** | −1.61 | — | −0.80 | — |
| **Paper (DDIC ref)** | −0.68 | — | −0.52 | — |

**Key findings [CLAIM]**:
1. **Direction match**: On paper-specific scenarios, DDIC < adaptive < no-control (matches paper ranking on cum_rf)
2. **Magnitude mismatch**: ANDES results 5–7× smaller than paper. LS1 DDIC cum_rf −0.099 (ANDES) vs −0.68 (paper); LS2 DDIC −0.017 (ANDES) vs −0.52 (paper)
3. **Relative gain preserved**: DDIC beats adaptive LS1 by 27% (−0.099 vs −0.136), LS2 by 50% (−0.017 vs −0.034) on cum_rf. Paper shows DDIC beats adaptive by ~27% on paper Eq.14 metric (inferred from Fig.6–9)
4. **Max_df**: DDIC seed44 is 9% worse than adaptive on LS1 max_df (0.507 vs 0.464 Hz), and 7% better on LS2 (0.308 vs 0.332 Hz)

**Interpretation [CLAIM]**: Paper-specific scenarios are now **tested and documented**. The 5–7× gap in magnitude is attributed to backend differences (ANDES vs Simulink) and reward formula scaling (PHI_F=100 paper vs 10,000 project). The relative ranking is preserved, supporting qualitative alignment but not magnitude reproduction.

---

## 2.5 Phase 7: Per-Agent PHI_F Boost Attempt (REJECTED)

**Hypothesis [CLAIM]**: Agent 3 (ES3 at Bus 14) receives weak gradient signal due to task asymmetry (Bus 14 disturbances are out-of-distribution in random test set; Bus 14 is agent 3's home bus where it contributes least). Boost ES3's reward weight by raising PHI_F for that agent.

**Design [FACT]**: Asymmetric reward shaping — set PHI_F_per_agent = [10000, 10000, 30000, 10000] (agent 3 gets 3× boost) while others stay 10000. Baseline PHI_F_all_agents = 10000 (Phase 4).

**Result [FACT]**: Per-agent agent_state probe (`results/harness/kundur/agent_state/agent_state_phase7_seed42_pilot.json`):
- Agent 2 (a2, ES3) share: 13.1% → **9.1%** (dropped, opposite of expected)
- Agent 1 (a1, ES2) share: 62.6% → 63.2% (unchanged dominance)
- Imbalance ratio a1/a2: 8.8× → **57.5×** (WORSE, spread 6.5×)

**Conclusion [CLAIM]**: Per-agent reward shaping **cannot fix structural dominance** because root cause is physical position (Bus 14 is sited at ES3 but disturbance hits at step 0 when no action yet taken; ES3 still learns defensively, ceding control to ES2 which has better observability of Bus 8 network effects). Phase 7 confirms this is not a learning/reward signal issue; it's an architectural constraint (decentralized observation + 0.2s control delay).

**Decision**: Phase 7 rejected. Not included in final DDIC results (all final results from Phase 4, PHI_ABS=0, symmetric PHI_F=10000).

---

## 2.6 Phase 9: Shared-Param SAC (Reference for Phase 10)

**Hypothesis [CLAIM]**: Train a single SAC agent on all 4 agents' combined observations/actions. Establish a shared-parameter baseline before testing warmstart.

**Result [FACT]**: 3-seed × 500ep shared-param SAC. Mean cum_rf_total −1.069 (per-seed: seed42→−1.356, seed43→−0.924, seed44→−0.927) [FACT: `results/andes_phase9_shared_seed42_500ep/eval_paper_grade_v2.json`]. Shared-param performs comparably to Phase 4 individual agents (Phase 4 mean −1.156), with lower bottom-seed variance but not better mean.

**Decision**: Phase 9 provides the warmstart source ckpt for Phase 10. Not adopted as production policy.

---

## 2.7 Phase 10: Shared-Param Warmstart Pilot (REJECTED)

**Hypothesis [CLAIM]**: Initializing all 4 independent SAC actors from the same pre-trained shared-param actor (`results/andes_phase9_shared_seed42_500ep/agent_shared_final.pt`) reduces seed-to-seed variance (std 0.227→<0.15) and per-agent dominance (a1 share 50–74%→<50%). Root motivation: trajectory analysis (§4.1 / §4.2) shows dominance locks by ep 100 from initialization, not from training dynamics — same init might break the lock.

**Method [FACT]**: Actor-only warmstart (shared weights → 4 per-agent actors; critics start fresh). Script: `scenarios/kundur/train_andes_warmstart.py`. Same hyperparameters as Phase 4 (comm_fail_prob=0.1, 500 ep, seeds 42/43/44). Wall: 1h40min (1.5× faster than Phase 4 plain SAC). Eval: 50 test eps per seed, env.seed 20000–20049. All 3 seeds reached 500 ep [FACT: `results/andes_warmstart_seed{42,43,44}/monitor_checkpoint.json` — `_episode_rewards` length=500].

**Results [FACT]**:

| Seed | Phase 4 cum_rf | Warmstart cum_rf | Delta |
|------|---------------|-----------------|-------|
| 42   | −1.1910       | −1.0286         | +0.162 (seed-level improvement) |
| 43   | −1.3641       | −1.3926         | −0.029 (marginal regression) |
| 44   | −0.9143       | −1.3232         | −0.409 (large regression) |
| n=3 mean | −1.1565  | −1.2481         | −0.092 (−7.9% WORSE) |
| n=3 std  | 0.2269   | 0.1932          | −0.034 (−14.8% LOWER) |

[FACT: `results/andes_warmstart_seed{42,43,44}/eval_paper_grade.json` — `summary.cum_rf_total`]

**Dominance structure [CLAIM]**: A1 probe (action cosine + magnitude proxy, A2 ablation not run):
- Seeds 42/43: action ratios 2.6× / 2.1× vs Phase 4 8.8× / 11.5× — partial redistribution
- Seed 44: ratio 9.3× (unchanged from Phase 4 13.1×, warmstart failed to redistribute)
- Dominant agent shifts: a0 (seed 42), a3 (seed 43), a1 (seed 44) vs Phase 4 consistent a1 dominance — structural reshuffling without performance improvement
[FACT: `results/harness/kundur/agent_state/agent_state_warmstart_seed{42,43,44}_final.json` — `phase_a1_specialization`]

**Bootstrap CI (per-ep pooled, 150 eps, seed=7919, n_resample=1000)**:
- Phase 4: [−0.02591, −0.02064]
- Warmstart: [−0.02789, −0.02223]
- CIs partially overlap → difference not statistically significant, but direction consistently negative

**Verdict [CLAIM]: WARMSTART_WORSE** — gate fires per pilot plan (`quality_reports/audits/2026-05-04_warmstart_pilot_plan.md`). The std reduction (−14.8%) is insufficient to offset the mean degradation (−7.9%). Seed 44 regression (−0.409) is the primary driver: Phase 4 seed 44 was the best-performing seed (−0.914), and warmstart pulled it toward the shared-param mean (−1.069), destroying the lucky initialization advantage. The warmstart actor appears too rigid (shared-param behavior locked in) for seeds where random init found a better basin.

**Decision**: Phase 10 hypothesis rejected. Seeds 45/46 warmstart extension not run. Phase 4 (mean −1.1565) remains production baseline. Filed as null result.

**File references**: Eval adapter: `scenarios/kundur/_eval_paper_grade_warmstart.py`; Verdict: `quality_reports/audits/2026-05-04_warmstart_pilot_verdict.md`

---

## 4. Root Cause Synthesis

### 4.1 Why DDIC/Adaptive Ratio is 1.03 (DDIC worse) Instead of 0.62 (DDIC better) (CLAIM)

**Factor 1: Reward formula sensitivity to system linearity**

Paper Eq.14–18 define r = −[PHI_F (Δf)² + PHI_H (ΔH)² + PHI_D (ΔD)²]. In Simulink's detailed nonlinear models, disturbance responses are rich (fast transients, complex harmonic content). Simple adaptive rules (proportional-derivative) can only approximate the nonlinear dynamics → SAC, which learns implicit nonlinear feedback, offers genuine advantage.

In ANDES TDS with phasor-equilibrium approximation (quasi-steady-state assumption), dynamics are simpler and more linear. Adaptive rules with proper tuning (K-grid search, Phase 4: K_H=10, K_D=400) can nearly saturate the learnable signal space. SAC's value-add shrinks.

**Factor 2: Per-agent capacity imbalance**

Agent 1 dominance (50–74% reward share) means DDIC is not a true multi-agent system in effect. A single well-positioned agent can solve a significant fraction of the control problem. Multi-agent SAC's coordination overhead (credit assignment, decentralized observation) doesn't pay off when one agent is dominant. An equivalent single-agent system scaled to agent 1's authority might match DDIC's performance.

**Factor 2b: Dominance is locked by ep 100, not training-emergent (FACT)**

Checkpoint trajectory analysis (`results/andes_ckpt_trajectory_phase4_seed42/trajectory.md`, 5 ckpts × 5 ablations × 10 fixed seeds = 250 rollouts) shows agent 1 share at:

| ep | a0 | a1 | a2 | a3 |
|---|---|---|---|---|
| 100 | 2.0% | **56.6%** | 5.8% | 35.5% |
| 200 | 5.6% | **57.5%** | 10.2% | 26.6% |
| 300 | 3.6% | **72.8%** | 5.5% | 18.1% |
| 400 | 0.9% | **56.2%** | 19.0% | 23.9% |
| 500 | 7.3% | **57.4%** | 10.9% | 24.5% |

Agent 1 holds 56.6% of authority by ep 100 — within 1pp of its ep 500 value (57.4%). This means dominance is **SAC initialization-driven (or first-100-ep position-driven), NOT training-emergent**. Extending training to 1000 or 2000 episodes will not redistribute. The fix must come from initialization asymmetry, capacity constraints, or reward-symmetry redesign — not from longer training. Phase 7 (per-agent PHI_F boost), Phase 8A (DT=0.1s), and Phase 8B (own-action obs) all attempted architectural escapes and all returned negative results, confirming the structural lock.

**Factor 3: Control step timing at 0.2 s**

Peak frequency deviation (max_df) occurs at disturbance step 0 (impulse response). Agent first acts at step 1. The immediate transient is **physically uncontrollable** by any feedback. DDIC and adaptive both see the same hard limit here, so no learning advantage emerges on max_df metric.

### 4.2 Per-Agent Failure Clustering on PQ_Bus14 (CLAIM)

All three training seeds show 3–4 of 5 worst-case episodes clustered on PQ_Bus14 disturbances, with identical worst-k disturbance magnitude 1.80 p.u (= worst_magnitude_median_pu from agent_state probe). This is not random stochasticity; it's **structural vulnerability**.

**Physical explanation [CLAIM]**:

- Disturbance location (Bus 14) is where agent 2 (ES3) is sited
- ES3 sees the disturbance at its local bus first, with no upstream filtering
- But agent 2 learned to contribute only 5–17% of total control action (from reward-share ablation, Phase 5)
- Agents 0/1/3, whose actions propagate to Bus 14 over network delays, cannot react fast enough
- Result: max_df (peak frequency deviation in Hz) for PQ_Bus14 disturbances reaches 0.33–0.45 Hz (worst-k observed across 3 seeds), consistent with the disturbance magnitude floor

If agent 2 had been allocated 50% of authority (matching agent 1), this bus-clustering might not occur. But achieving equal authority allocation requires either:
1. Asymmetric network observations (e.g., agent 2 sees disturbance predictor), or
2. Position-aware reward shaping (agents at "critical" buses get higher PHI coefficients), or
3. Architectural redesign (role-based single-agent per bus vs multi-agent SAC)

None of these are in paper Eq.14.

---

### 4.3 Cross-Backend Dominance Test: ANDES vs Simulink (2026-05-04)

**Question**: Is agent dominance (50–74% on agent 1) an ANDES-specific artifact or a universal SAC/topology property?

**Method**: Port agent_state probe to Simulink-trained DDIC checkpoints (5 file diffs; `--backend simulink` CLI flag). Run Phase A1 (action-space specialization — no MATLAB engine required) on 3 screen ckpts from 2026-05-03 training sweep.

**A1 results** (action pairwise cosine similarity):

| Ckpt | offdiag_cos_mean | A1 verdict |
|---|---|---|
| ANDES seed42 | +0.352 | partially homogeneous |
| ANDES seed43 | +0.318 | partially homogeneous |
| ANDES seed44 | +0.310 | partially homogeneous |
| Simulink screen_h1 (phi_f 200) | −0.040 | SPECIALIZED |
| Simulink screen_h2 (es3 4×) | +0.145 | SPECIALIZED |
| Simulink screen_h3 (es3 10×) | −0.082 | SPECIALIZED |

ANDES agents are approaching homogeneous (positive cosine, 0.31–0.35); all Simulink ckpts are highly specialized (negative or near-zero cosine). This is a **clean cross-backend divergence** on A1.

**Interim verdict [CLAIM, 3 Simulink observations]**: ANDES-SPECIFIC-LIKELY. Simulink training (with per-agent reward shaping) produces differentiated agents. ANDES training does not. The dominance pattern in §4.1 is likely a joint product of ANDES phasor linearization and ANDES reward imbalance — not inherent to the SAC/DDIC topology.

**Caveat**: A1 measures policy differentiation, not reward attribution. A2 (ablation) is the definitive dominance test and requires live MATLAB engine (~58 min/ckpt). A2 port is complete (`--backend simulink --phases A2`); pending MATLAB engine availability. Until A2 runs, "ANDES-specific" remains a hypothesis, not a falsification-gate verdict.

**Impact on §4.1 claim**: If A2 confirms Simulink agents do NOT show 50–74% dominance, the "multi-agent framework decorative" finding is ANDES-backend-specific. If A2 shows same dominance despite A1 differentiation, the root cause is physical topology (not backend), and the claim generalizes.

See `quality_reports/audits/2026-05-04_andes_simulink_cross_backend_dominance.md` for full table and port details.

---

## 5. Honest Claims

1. **DDIC beats no-control decisively**: 3.65× on cum_rf, 33% on osc. This is unambiguous across all three seeds.

2. **DDIC vs adaptive on cum_rf (n=5 update)**: n=5 mean -1.186 (DDIC) vs -1.060 (best adaptive K=10/400). DDIC is 12% **worse** on cum_rf. The n=5 95% CI [-1.515, -0.857] [half-width=0.329, t(4,0.025)=2.776]. Best adaptive (-1.060) **remains within** the CI → **no statistically significant difference** at n=5. Gate A3 → Tier B recommended. DDIC **wins on oscillation**: 0.103 Hz (DDIC) vs 0.115 Hz (adaptive), a 10% improvement.

3. **DDIC loses on peak frequency excursion**: max_df mean 0.234 Hz (DDIC) vs 0.215 Hz (adaptive). DDIC is 9% worse. This is consistent across all three seeds. On paper-specific LS1 scenario, DDIC is also worse (0.507 vs 0.464 Hz, 9% penalty).

4. **DDIC/adaptive performance ratio reversed from paper**: Our ratio 1.03 (DDIC worse on cum_rf) vs paper 0.62 (DDIC better). The 40% directional flip is attributed to system-specific differences (Simulink detailed dynamics vs ANDES phasor linearized), per-agent capacity imbalance (single-agent dominance), and control-step timing constraints.

5. **The multi-agent framework is functional but not robust**: Capacity imbalance (agent 1 = 50–74%, others = 26–50% combined) drives the performance. Removing agent 1 degrades performance 62–70%. This is single-point-of-failure architecture, not resilient multi-agent design.

6. **Failure clustering is systematic, not noise**: All three seeds fail on the same bus (Bus 14) with max_df reaching 0.33–0.45 Hz. Structural vulnerability, not stochastic variance.

7. **Project deviations are documented but material**: PHI_F rebalance (100→10,000), PHI_D reduction (1.0→0.02), PHI_ABS ablation (50→0), D_FLOOR raise (0.1→1.0), action range narrowing (ΔH ±[100,300]→[−5,15], ±133× on ΔD) collectively shift the optimization landscape. Absolute numbers are not paper-comparable. Qualitative ranking on paper-specific scenarios (DDIC < adaptive < no-control on cum_rf) is preserved; on random test set (env.seed 20000–20049), ranking reverses (adaptive < DDIC on cum_rf by 3%).

---

## 6. Limitations and Future Work

The following are **not** investigated or are only partially resolved:

1. **Paper's specific disturbance scenarios** (§3.3 NOW TESTED): Validated on LS1 (−248 MW Bus14) and LS2 (+188 MW Bus15) with DDIC seed 44, showing relative ranking match but 5–7× magnitude gap. Future work: replicate with all 3 training seeds and 100-episode random seeds for statistical robustness.

2. **Statistical sample updated to n=5** (Tier A, 2026-05-04). Cross-seed std 0.265 (22% of mean -1.186). n=5 95% CI [-1.515, -0.857] (half-width=0.329, vs n=3 half-width≈0.564). Best adaptive (-1.060) **still within** CI → Gate A3: proceed to Tier B (n=10) for conclusive separation or accept stat-tie framing.

3. **Adaptive baseline is project proxy, not exact [25] formula.** We use generic proportional-derivative adaptive law (k_H |dω̇|, k_D |Δω|). Paper references Fu et al. 2022, which may have tighter tuning. K-grid optimization (Phase 4) was heuristic (5×5 sweep), not exhaustive.

4. **Convergence at 500 episodes may be premature.** Paper states "stable after 500 ep" but with different reward formula. Our PHI_ABS ablation may shift convergence point. Longer training (2000 ep) untested.

5. **New England 39-bus system untested.** Does agent-state imbalance generalize to 10 agents? Do we see same-bus clustering?

6. **Faster control rate untested.** 0.2 s per step is relatively slow. 0.1 s or 0.05 s steps might allow earlier agent reaction to immediate transient, improving max_df.

7. **Observation augmentation untested.** Current obs: [f_local, f_neighbors, P_control, Q_control]. Adding [disturbance_prediction] or [network_distance_to_worst_bus] might help agents anticipate failure modes.

8. **Centralized Training Decentralized Execution (CTDE) untested.** Paper assumes independent SAC agents. Shared critic during training might improve credit assignment.

---

## 7. Reproducibility

All training runs, evaluations, and probes are archived:

| Category | Path | Details |
|---|---|---|
| Phase 1 (D-Floor) | `results/andes_dfloor_seed{42..46}/` | 5 seeds, 100 ep each, D_FLOOR=1.0, Option A+D fixes |
| Phase 2 Tuning | in-conversation diagnostics (no separate run dir) | PHI_F/PHI_D rebalance via manual sweeps |
| Phase 3 v1 (Flawed) | `results/andes_phase3_seed{42,43,44}/` | 500 ep, different test seeds (deprecated) |
| Phase 3 v2 (Fixed test set) | `results/andes_phase3_eval_v2/` | Re-eval all methods on fixed seeds 20000–20049 |
| Phase 4 (PHI_ABS=0) | `results/andes_phase4_noPHIabs_seed{42,43,44}/` | 500 ep, PHI_ABS=0 (canonical training) |
| Phase 4 Adaptive K-grid | `results/andes_adaptive_kgrid/` | 5×5 K-grid sweep + top 3 full 50-ep runs |
| Phase 5 Agent State | `results/harness/kundur/agent_state/agent_state_phase4_seed{42,43,44}_final.json` | Specialization, ablation, failure clustering probes |
| Phase 6 PHI_ABS=10 (aborted) | `results/andes_phase6_phiabs10_seed42/` (partial, 50 ep) | Hypothesis test; aborted after P0 structural findings |
| Phase 7 Per-Agent PHI_F (rejected) | `results/harness/kundur/agent_state/agent_state_phase7_seed42_pilot.json` | Asymmetric PHI_F boost attempt on ES3; imbalance ratio worsened 6.5×; architectural constraint confirmed |
| Paper-Specific Scenarios (validated) | `results/andes_eval_paper_specific/summary.md` | LS1 (Bus14 −248 MW) and LS2 (Bus15 +188 MW) tested with DDIC seed 44 and adaptive K=10/400 |
| Phase 9 Shared-Param SAC | `results/andes_phase9_shared_seed42_500ep/` | 3-seed × 500ep shared-param SAC; mean cum_rf −1.069; warmstart source for Phase 10 |
| Phase 10 Warmstart Pilot (REJECTED) | `results/andes_warmstart_seed{42,43,44}/` | Actor-only init from Phase 9 ckpt; n=3 mean −1.248 (7.9% worse than Phase 4); WARMSTART_WORSE; null result |

**Code references**:

- SAC agent + multi-agent manager: `agents/sac.py`, `agents/ma_manager.py`
- ANDES environment: `env/andes/base_env.py`
- Kundur training script: `scenarios/kundur/train_andes.py`
- Evaluation and baseline probes: `scenarios/kundur/_phase3_eval_v2.py`, `_phase3_baseline_adaptive.py`
- Agent-state probe: `probes/kundur/agent_state/`

All phases documented in separate verdict files:
- `quality_reports/audits/2026-05-03_andes_dfloor_seed_sweep_verdict.md`
- `quality_reports/audits/2026-05-03_andes_phase3_3way_verdict.md`
- `quality_reports/audits/2026-05-03_andes_phase3_v2_p0_fixes_verdict.md`
- `quality_reports/audits/2026-05-03_andes_phase4_phi_abs_ablation_verdict.md`
- `quality_reports/audits/2026-05-03_andes_agent_state_3seed_verdict.md`
- `quality_reports/audits/2026-05-03_andes_phase6_phi_abs_10_aborted_verdict.md`
- `quality_reports/audits/2026-05-04_warmstart_pilot_verdict.md`

---

## 8. Conclusion

We report an honest, instrumented reproduction of Yang et al. 2023 DDIC on the ANDES Kundur 4-ESS system. DDIC achieves meaningful improvement over uncontrolled baseline (3.65× on cum_rf, 33% on oscillation). However, **DDIC loses to the best tuned adaptive controller** on the primary metric: 3% worse cum_rf (−1.093 vs −1.060), with no statistical significance at n=3 (95% CI overlaps adaptive's point estimate). DDIC wins on oscillation (10% better) but loses on peak transient (9% worse max_df). The DDIC/adaptive **ratio reversed from paper**: our 1.03 (DDIC worse on cum_rf) vs paper's 0.62 (DDIC better), a 40% directional flip.

**Paper-specific disturbances validated** (§3.3): On LS1 (−248 MW Bus14) and LS2 (+188 MW Bus15), DDIC shows the same ranking as paper (DDIC < adaptive < no-control on cum_rf), but magnitudes are 5–7× smaller (ANDES −0.099 vs paper −0.68 on LS1 cum_rf), attributed to backend and reward formula differences.

The multi-agent framework exhibits **functional capacity but structural imbalance**: agent 1 (ES2 at Bus 16) dominates, contributing 50–74% of total control authority. Phase 7 attempted per-agent reward shaping to boost agent 3; imbalance ratio worsened 6.5×, confirming the root cause is **architectural/physical** (decentralized observation + 0.2s control delay), not learning signal.

Our diagnostic work isolated five root causes:
1. Reward magnitude imbalance (fixed by 100× PHI_F boost, 50× PHI_D reduction, PHI_ABS=0)
2. D-floor attractor (fixed by raising floor from 0.1 to 1.0)
3. Per-agent capacity imbalance (structural; Phase 7 rejected attempt to fix)
4. Test set asymmetry (fixed by moving to fixed env.seed 20000–20049)
5. System-specific signal saturation (ANDES phasor dynamics simpler than Simulink EMT; adaptive control saturates learnable space)

**Verdict**: DDIC is **not better than adaptive on ANDES**. The multi-agent learning advantage claimed in the paper **does not transfer to this phasor-level simulator**. Future work should investigate whether the gap is fundamental (inherent to phasor linearization) or addressable (deeper network architecture, observation augmentation, or Simulink-side tuning of adaptive K for equivalence).

---

## References

- Yang, Q., Zhang, P., Zhao, B., & Wu, K. (2023). Multi-Agent Deep Deterministic Policy Gradient for Virtual Synchronous Generator Control. IEEE Transactions on Power Systems.
- Fu et al. (2022). [Adaptive VSG control citation — exact reference not retrieved from project docs].

---

*Pre-draft compiled from 6 diagnostic audits totaling ~6 GPU-hours (1× 5-seed D-floor sweep 100ep, 2× 3-seed full training 500ep, 3× 1-seed ablations/probes). Ready for expert review and content verification before archival.*
