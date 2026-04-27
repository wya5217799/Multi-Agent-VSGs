# R1 Verdict — Reward formula audit (read-only) — NO BUG

> **Status:** PASS — `_compute_reward` implements paper Yang 2023 Eq.14-18 mathematically faithfully. Δω in p.u. is paper-stated (Sec.II-A). The `(ΔH_avg)²` and `(ΔD_avg)²` forms match Eq.17-18. The plateau / regression observed in P4.2-overnight + P5.1 is **not caused by reward formula bugs**; it is caused by **PHI weighting + Q7 ΔH dimensional ambiguity**, both addressable in R2 (PHI re-sweep) without touching the reward source.
> **Date:** 2026-04-27
> **Predecessor:** P5.1 paper-eval verdict (DDIC −19 % WORSE than zero-action).
> **Mode:** read-only audit; no code edits.

---

## 1. Source location

[`env/simulink/_base.py:191-251`](../../../../env/simulink/_base.py) — `_SimVsgBase._compute_reward` (single source-of-truth for both Kundur and NE39 Simulink envs; the kundur-specific env does not override).

---

## 2. Paper-side reference

[`docs/paper/yang2023-fact-base.md` §3.4](../../../../docs/paper/yang2023-fact-base.md):

- **Eq.14 (total):** `r_{i,t} = φ_f r^f_{i,t} + φ_h r^h_{i,t} + φ_d r^d_{i,t}`
- **Eq.15 (r_f):** `r^f_{i,t} = −(Δω_{i,t} − Δω̄_{i,t})² − Σ_j (Δω^c_{i,j,t} − Δω̄_{i,t})² · η_{j,t}`
- **Eq.16 (ω̄_i):** `Δω̄_{i,t} = (Δω_{i,t} + Σ_j Δω^c_{i,j,t} η_{j,t}) / (1 + Σ_j η_{j,t})`
- **Eq.17 (r_h):** `r^h_{i,t} = −(ΔH_{avg,i,t})²`
- **Eq.18 (r_d):** `r^d_{i,t} = −(ΔD_{avg,i,t})²`
- **φ_f=100, φ_h=1, φ_d=1** (Sec.IV-B explicit)
- **Δω unit (Sec.II-A line 50, fact-base ./§2.1):** "频率偏差 (p.u., 相对于额定角频率)" = **p.u.**, dimensionless.

Sec.IV-C evaluation cumulative reward (different from training r_f):
- `−Σ_t Σ_i (Δf_{i,t} − f̄_t)²` where Δf is in **Hz** and f̄_t is the **GLOBAL** mean (not local ω̄_i).

Paper deliberately uses different metrics for training vs evaluation. Both are paper-faithful.

---

## 3. Code-vs-paper line-by-line audit

| Item | Paper formulation | Code line(s) | Match? |
|---|---|---|---|
| Total reward shape | r_i = φ_f r_f + φ_h r_h + φ_d r_d | L232-244: `rewards += PHI_F·r_f_i`; `rewards −= PHI_H·r_h_val`; `rewards −= PHI_D·r_d_val`. Net effect: `rewards = PHI_F·r_f − PHI_H·(ΔH_avg)² − PHI_D·(ΔD_avg)²`, equivalent to `+φ_f r_f + φ_h r_h + φ_d r_d` because `r_h_val = (ΔH_avg)² ≥ 0` and `r_h = −r_h_val`. | ✓ Mathematically equivalent |
| Δω unit | p.u. (Sec.II-A line 50) | L217: `dw_pu = self._omega − 1.0` (ω in p.u. with nominal=1.0; Δω = ω−1) | ✓ Match |
| ω̄_i (Eq.16, local weighted mean of self + active neighbors) | (Δω_i + Σ Δω^c_j η_j) / (1 + Σ η_j) | L221-225: builds `group_dw = [dw_pu[i]] + [dw_pu[nb] for nb in neighbors if comm_mask]` then `omega_bar_i = mean(group_dw)`. mean over (1 + n_active) elements is exactly the paper Eq.16 weighted mean. | ✓ Mathematically equivalent |
| r_f (Eq.15, paper) | `−(Δω_i − ω̄_i)² − Σ_j (Δω^c_j − ω̄_i)² η_j` | L227-230: `r_f_i = −(dw_pu[i] − omega_bar_i)²; for nb,η: r_f_i −= (dw_pu[nb] − omega_bar_i)² × η_j` | ✓ Match |
| r_f weighted by φ_f | rewards[i] += φ_f · r_f_i | L232: `step_r_f = self._PHI_F * r_f_i; rewards[i] += step_r_f` | ✓ Match |
| r_h (Eq.17): `−(ΔH_avg)²` | global mean of ΔH then square | L237-238: `delta_H_mean = mean(delta_M) / 2.0; r_h_val = delta_H_mean ** 2`. Note **ΔH = ΔM/2** is project Q7 working hypothesis (M = 2H project convention, paper does NOT specify). r_h_val is the squared global mean. | ⚠ Formula form ✓; ΔH=ΔM/2 is **Q7 inference**, not paper-stated. If paper uses ΔH=ΔM (no factor 2), then code r_h is 4× too small. |
| r_h weighted by φ_h | rewards −= φ_h · r_h_val | L239: `rewards −= self._PHI_H * r_h_val` | ✓ Match |
| r_d (Eq.18): `−(ΔD_avg)²` | global mean of ΔD then square | L242-243: `delta_D_mean = mean(delta_D); r_d_val = delta_D_mean ** 2` | ✓ Match |
| r_d weighted by φ_d | rewards −= φ_d · r_d_val | L244: `rewards −= self._PHI_D * r_d_val` | ✓ Match |
| Components dict | per-step `{r_f, r_h, r_d}` | L246-249: `{"r_f": r_f_total/n, "r_h": −PHI_H·r_h_val, "r_d": −PHI_D·r_d_val}` | ✓ Exposed for downstream observability; `r_f_total/n` returns avg per-agent r_f (numerically same as per-agent value since the formula already has loop) |

---

## 4. Findings

1. **Reward formula is structurally correct.** No discrepancy between code and paper Eq.14-18. Δω is in p.u., consistent with paper Sec.II-A line 50 fact-base.
2. **Q7 (ΔH = ΔM / 2) inference still active.** Code uses `delta_M / 2` for r_h. If paper uses `ΔH = ΔM` (no factor 2), code r_h is 4× smaller than paper-faithful. This affects PHI_H tuning, but does NOT cause the DDIC-vs-no-control regression seen in P5.1.
3. **PHI override (1e-4 vs paper 1.0) is the runtime culprit, not formula bug.** With PHI_H=PHI_D=1e-4 + observed ΔH range [−3, +9] from `_decode_action` (`DM_MIN=-6`, `DM_MAX=+18`, ΔH=ΔM/2), the raw r_h_val = (mean ΔH)² has typical magnitude ~5 per step (50-step sum ~290). Multiply by PHI_H=1e-4 → per-ep |r_h| ~0.029 (matches P4.2-overnight observation). r_f at typical (Δω−ω̄)² ~ 1e-5 × PHI_F=100 → per-step ~1e-3, per-ep |r_f| ~0.005 (also matches). So r_h dominates ~6× r_f → 70% of total reward magnitude.
4. **Train-side r_f vs eval-side cumulative reward use different metrics by paper design.** Training r_f uses LOCAL ω̄_i in p.u.; Sec.IV-C eval cumulative uses GLOBAL f̄_t in Hz. P5.1 evaluator implements eval-side correctly. NOT a code bug.

---

## 5. Conclusions

**No reward-formula bug.** The plateau (P4.2-overnight) and DDIC-vs-no-control regression (P5.1) are both downstream of:
- (a) PHI weighting that lets r_h dominate (`PHI_H=PHI_D=1e-4` × project's ΔM range), and
- (b) the Q7 ΔH=ΔM/2 inference modulating effective r_h scale.

Both are addressable in **R2 (PHI re-sweep with paper-style global-r_f gate)** without modifying the reward source.

R2 must:
- (a) include zero-action no-control eval as PASS gate (cum_unnorm_DDIC < cum_unnorm_no_control = −7.48);
- (b) sweep PHI candidates that materially shift r_h share away from 70 %:
  - `phi_h_d_lower` (1e-5/1e-5) — 10× lower PHI_H/D, ~7 % r_h share target
  - `phi_f_500` (PHI_F=500/1e-4/1e-4) — 5× higher PHI_F, alternative way to push r_f share up
  - `phi_paper_scaled` (1e-2/1e-2) — paper-style, 100× above current; tests whether the original P4.2 stopping rule chose wrong
- (c) skip `phi_b1` baseline re-run (already have P5.1 data: DDIC −8.90 vs no-control −7.48).

---

## 6. Boundary check

- `env/simulink/_base.py`: **read-only**, untouched.
- `env/simulink/kundur_simulink_env.py`: untouched (no override of `_compute_reward`).
- All Simulink + agent + helper paths untouched ✓
- NE39 untouched ✓

No code change in R1.

---

## 7. Output

This file only.

---

## 8. Next step

Proceed to **R2** (PHI re-sweep with paper-style gate). Authorized by user GO message: "R1R2 先做".

R2 design:

- 3 candidates (skip already-known `phi_b1`): `phi_h_d_lower`, `phi_f_500`, `phi_paper_scaled`.
- Each: 50-ep train + 50-scenario paper-style eval of `best.pt`. Compare against fixed no-control baseline (cum_unnorm = −7.48 from P5.1).
- Hard gate: `cum_unnorm_DDIC > cum_unnorm_no_control × 1.0` (DDIC magnitude smaller = better).
- Stop on first PASS.
- New env-var hook needed: `KUNDUR_PHI_F` (currently hardcoded to 100.0). One-line edit.
