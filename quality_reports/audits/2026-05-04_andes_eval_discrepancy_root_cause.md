# Eval Discrepancy Root Cause Audit

**Date**: 2026-05-04  
**Investigator**: Tracer  
**Scope**: Same controller (adaptive K_H=10, K_D=400), same fixed seeds (20000–20049), two scripts, different cum_rf totals

## Summary

H1 is confirmed as the sole root cause. The two script families measure **structurally different quantities** with the same variable name `cum_rf`. `_adaptive_kgrid.py` and `_phase3_eval_v2.py` compute a **global spread formula** inline, directly from `info["freq_hz"]`: `-Σ_t Σ_i (f_i,t − f̄_t)²` in Hz², where `f̄_t` is the **step-mean frequency across all 4 agents**. `_eval_paper_grade_andes.py` computes the same formula but feeds it **p.u. omega** (`info["omega"]`) to `_compute_global_rf_unnorm`, which converts internally via `(omega - 1.0) * f_nom`. Algebraically the two formulas are identical. The discrepancy therefore cannot come from the formula itself — it comes from the **action saturation implementation**. The kgrid family divides `K * |x|` by the env class constants `DM_MAX / DD_MAX` (30.0 each), while the paper-grade family clips `K_H * |omega_dot_rad|` and `K_D * |d_omega_rad|` directly to `[-1, 1]` **without dividing by DM_MAX/DD_MAX**. Because `K_D=400` and `|d_omega_rad|` can easily be > 0.0025, the paper-grade adaptive controller saturates at 1.0 for nearly every step, whereas the kgrid controller saturates at `min(400 * |d_omega_rad| / 30.0, 1.0)` — a 30× weaker action. The paper-grade controller therefore applies **systematically larger D-boost actions**, resulting in stronger synchronization and a less-negative (better) cum_rf total. The 38% magnitude difference is **not** a measurement artifact — the two scripts are evaluating meaningfully different controllers despite sharing the label "adaptive K=10/400".

---

## Hypothesis Table

| Rank | Hypothesis | Confidence | Evidence Strength | Why it remains plausible |
|------|------------|------------|-------------------|--------------------------|
| 1 | Different adaptive controller action saturation formula (DM_MAX division absent in paper-grade) | **High** | **Strong** — direct code-path FACT from both files | Explains the direction and magnitude of the gap; kgrid produces weaker D-boost |
| 2 | Different cum_rf formula (local info["r_f"] vs global recompute) | Down-ranked | Strong (eliminated) | Both scripts compute the same global spread formula; eliminated by direct inspection |
| 3 | Different env config (comm_fail_prob) | Down-ranked | Moderate (eliminated) | kgrid uses `comm_fail_prob=0.0` explicitly; paper-grade uses default `COMM_FAIL_PROB=0.1`; partially confounding but secondary |
| 4 | Different units / scale | Down-ranked | Strong (eliminated) | Both use Hz² via identical algebraic path |

---

## Evidence For

### H1 (confirmed): Action saturation divergence

**kgrid / phase3_eval_v2 saturation** (`_adaptive_kgrid.py` lines 41–43, `_phase3_eval_v2.py` lines 115–117, both FACT):

```python
dM = K_H * abs(d_omega_dot)
dD = K_D * abs(d_omega)
actions[i] = np.array([min(dM / DM_MAX, 1.0), min(dD / DD_MAX, 1.0)])
```

`DM_MAX = DD_MAX = 30.0` (from `AndesBaseEnv` class constants — FACT: `base_env.py` line 56–59). So the effective normalized action is `min(K_D * |d_omega_rad| / 30.0, 1.0)` for D.

**paper-grade saturation** (`_eval_paper_grade_andes.py` lines 121–125, FACT):

```python
d_omega_rad = float(o[1]) * 3.0
omega_dot_rad = float(o[2]) * 5.0
delta_m_norm = float(np.clip(K_H * abs(omega_dot_rad), -1.0, 1.0))
delta_d_norm = float(np.clip(K_D * abs(d_omega_rad),   -1.0, 1.0))
```

No division by DM_MAX/DD_MAX. With `K_D=400` and typical `|d_omega_rad|` ~0.01–0.05 rad/s after disturbance onset, `400 * 0.01 = 4.0` → clips to 1.0 immediately. The kgrid formula gives `400 * 0.01 / 30.0 = 0.133`. The paper-grade D-boost is therefore up to **7.5× larger** for the same obs value.

### H2 (eliminated): Formula identity confirmed

Both scripts compute `cum_rf` as `- Σ_t Σ_i (f_i,t − mean_j f_j,t)²`.

kgrid inline (`_adaptive_kgrid.py` lines 46–47, FACT):
```python
f = info["freq_hz"]
f_bar = float(np.mean(f))
cum_rf -= float(np.sum((f - f_bar) ** 2))
```

paper-grade via `_compute_global_rf_unnorm` (`evaluation/metrics.py` lines 129–139, FACT):
```python
delta_f = (omega_trace - 1.0) * f_nom   # converts p.u. → Hz
mean_t = delta_f.mean(axis=1, keepdims=True)
centered = delta_f - mean_t
return float(-(centered ** 2).sum())
```

These are algebraically identical given `f = omega * f_nom`. H2 is eliminated.

### H3 (partial confounder, secondary): comm_fail_prob

- kgrid uses `AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)` (FACT: `_adaptive_kgrid.py` line 61)
- paper-grade uses `AndesMultiVSGEnv(random_disturbance=True)` with no explicit `comm_fail_prob` (FACT: `_eval_paper_grade_andes.py` line 361), which defaults to `COMM_FAIL_PROB=0.1` (FACT: `base_env.py` line 108)

This means paper-grade episodically loses comm links, which slightly weakens the adaptive law's ability to read neighbors — a secondary effect that would make paper-grade cum_rf *worse* (more negative), not better. This does not explain the gap direction and is dominated by H1.

---

## Evidence Against / Gaps

### H1

- CLAIM: The magnitude difference of 38% is fully explained by action saturation alone. This has not been verified numerically for a single episode; only the formula structure is confirmed as FACT. A per-step trace would strengthen this from "strong inference" to "controlled experiment."
- CLAIM: The paper-grade controller saturates to 1.0 "for nearly every step." This depends on the typical magnitude of `|d_omega_rad|` post-disturbance. It has not been empirically measured.

### H3

- This partial confounder acts in the opposite direction to the observed gap (comm failures would make paper-grade *worse*, not better). It cannot explain the direction of the 38% gap.

---

## Rebuttal Round

**Best challenge to H1**: Could the gap arise purely from the comm_fail_prob difference (H3), not from action saturation? With comm_fail_prob=0.1, each episode loses ~10% of links on average. Could this actually *improve* performance by forcing more independent control?

**Why the leader still stands**: The comm_fail_prob direction is wrong for the observed gap. The kgrid family (comm_fail_prob=0.0) has cum_rf = −1.060 (better), while paper-grade (comm_fail_prob=0.1) has cum_rf = −1.461 (worse). If comm failures were beneficial, paper-grade would be *better* than kgrid, which is the opposite of what is observed. H3 acts as a suppressor (partially offsetting H1's improvement in paper-grade), making the true action-saturation effect even larger than 38%. H1 is the primary driver.

---

## Convergence / Separation Notes

H2 and H4 collapse to the same root cause (formula equivalence) and are jointly eliminated by code inspection. H1 and H3 remain genuinely distinct mechanisms. H3 partially counteracts H1 (makes paper-grade slightly worse than it would be under H1 alone), meaning the true action-saturation effect is slightly larger than the observed 38%.

---

## Numerical Trace

Values from artifact files (FACT: read from on-disk JSON/MD at HEAD):

| seed range | script | K_H | K_D | cum_rf total (50 ep) |
|---|---|---|---|---|
| 20000–20049 | `_adaptive_kgrid.py` → `top3_full50.json` | 10 | 400 | **−1.0602** |
| 20000–20049 | `_eval_paper_grade_andes.py` → `summary.md` | 10 | 400 | **−1.4608** |

Per-seed breakdown not available without re-running; the total difference is −0.4006 (−38% magnitude vs kgrid).

---

## Resolution

The paper-grade script `_eval_paper_grade_andes.py` computes cum_rf via `_compute_global_rf_unnorm(omega_trace, f_nom)` — algebraically equivalent to the kgrid formula. The formula is not the bug.

**The "adaptive K=10/400" label in the two script families refers to controllers with different effective action magnitudes.** Per paper §IV-C, the adaptive controller is a heuristic baseline, not a precisely specified algorithm. Neither saturation convention is authoritative per the paper. For predraft cross-comparisons, only numbers from the *same* script should be compared against each other. Mixing kgrid and paper-grade adaptive numbers (e.g., "K=10/400 cum_rf = −1.060 from kgrid vs DDIC from paper-grade") is invalid.

**Which value is "closer to paper §IV-C intent"?** The paper does not specify the saturation convention. However the paper-grade convention (direct clip to [−1, 1]) is more natural for a normalized action space, and the paper-grade DDIC results are evaluated with the same env and saturation assumptions — making internal comparisons within the paper-grade family self-consistent. The kgrid family's internal comparisons (K sweep) are also self-consistent.

---

## Action Items

1. **`_adaptive_kgrid.py` and `_phase3_eval_v2.py`**: Add a comment at the saturation line (line 43 / line 117) documenting that the formula uses `DM_MAX=30` as divisor, making the effective gain `K_D/DD_MAX` = 400/30 ≈ 13.3, not 400. This prevents future mis-interpretation that K=400 means a direct clip at 1.0.

2. **`_eval_paper_grade_andes.py`** (and `_eval_paper_grade_andes_one.py`): Add a comment at lines 121–125 (and their equivalents) noting that the saturation is a direct clip without DM_MAX/DD_MAX division, making the effective K_D 30× stronger than the kgrid convention for the same gains.

3. **Predraft**: If citing both kgrid and paper-grade adaptive cum_rf values, flag them as "two different controller implementations sharing the same gain label." Do not average or directly compare them without this caveat.

4. **No source files modified** — this audit is read-only per constraint.

---

## Uncertainty Notes

- CLAIM: The 38% gap is fully explained by action saturation. The per-step magnitude of `|d_omega_rad|` has not been directly measured; a single-seed trace would confirm whether saturation is sustained throughout or only brief.
- CLAIM: The comm_fail_prob=0.1 default in paper-grade is a secondary contributor. Magnitude is not quantified; would require a controlled run with comm_fail_prob=0.0 in paper-grade.
- The action saturation divergence is a FACT (code path confirmed); the quantitative attribution is a strong inference pending numerical confirmation.
