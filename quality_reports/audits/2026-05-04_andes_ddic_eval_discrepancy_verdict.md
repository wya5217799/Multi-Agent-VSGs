# DDIC Eval Discrepancy Audit — `comm_fail_prob` Mismatch

**Date**: 2026-05-04
**Author**: Claude (probe + code-diff)
**Status**: ROOT-CAUSE-IDENTIFIED
**Severity**: predraft headline number `−1.093` is **eval-condition artifact**, not the apples-to-apples paper-faithful metric.

---

## 1. The discrepancy

The predraft cites Phase 4 (PHI_ABS=0) DDIC 3-seed mean cum_rf as `−1.093`. Two evaluations of the **same** Phase 4 checkpoints on the same FIXED_TEST_SEEDS=[20000..20049] give different headline numbers:

| Eval script | comm_fail_prob | 3-seed mean cum_rf | Source |
|---|---:|---:|---|
| `_phase4_eval.py` | **0.0** (explicit) | **−1.093** | `results/andes_phase4_eval/summary.json` (5-3 17:44) |
| `_eval_paper_grade_andes_one.py` (parallel) | **0.1** (default) | **−1.156** | `results/andes_eval_paper_grade/per_seed_summary.json` (5-4 05:05) |

Per-seed breakdown (Phase 4 PHI_ABS=0 _final_):

| Seed | phase4_eval | paper_grade | Δ |
|---:|---:|---:|---:|
| 42 | −1.0987 | −1.1910 | +8.4% (paper_grade more negative) |
| 43 | −1.3041 | −1.3641 | +4.6% |
| 44 | −0.8763 | −0.9143 | +4.3% |
| **mean** | **−1.0930** | **−1.1565** | **+5.8%** |

(`_phase3_eval_v2.py` exists in the repo but evaluates **pre-ablation** ckpts at `results/andes_phase3_seed{N}`, not Phase 4 ckpts at `results/andes_phase4_noPHIabs_seed{N}`. It is **not** an apples-to-apples comparison and is excluded from this audit. The two scripts are byte-identical except for `OUT_DIR` and `ckpt_dir` strings.)

---

## 2. Root cause

### 2.1 phase4_eval ≠ paper_grade: `comm_fail_prob` is different

`scenarios/kundur/_phase4_eval.py:33`:
```python
env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)
```

`scenarios/kundur/_eval_paper_grade_andes_one.py:262`:
```python
env = AndesMultiVSGEnv(random_disturbance=True)  # comm_fail_prob NOT passed
```

`env/andes/base_env.py:137`:
```python
self.comm_fail_prob = comm_fail_prob if comm_fail_prob is not None else self.COMM_FAIL_PROB  # 0.1
```

→ phase4_eval evaluates at **0% comm failure**, paper_grade at **10% comm failure (per-link, per-reset)**.

### 2.2 Training used `comm_fail_prob=0.1`

`scenarios/kundur/train_andes.py:136`:
```python
env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.1)
```

→ Training condition matches paper_grade eval, **mismatches** phase4_eval.

### 2.3 Why DDIC degrades under comm failure

DDIC obs vector includes neighbor `omega` and `omega_dot` (two ring neighbors per agent). When a link fails (`comm_eta=0`), the receiving agent gets zero for that neighbor signal. This is the same condition the policy was trained under, so it knows how to act, but each missing signal removes coordination information → expected degradation per ep.

Adaptive controller uses only `obs[i][1]` and `obs[i][2]` (local Δω and ω̇) — no neighbor info → comm failure does not affect it. This is consistent with paper_grade adaptive K=10/400 cum_rf_total = −1.0602 being a clean apples-to-apples metric.

---

## 3. Class of bug

This is the **same root-cause class** as the adaptive saturation bug fixed earlier:

| Bug | Class | Location | Status |
|---|---|---|---|
| Adaptive K=10/400 saturation | Eval-script ≠ paper formula | `_phase3_eval_v2.py` adaptive impl | ✅ FIXED in `_paper_grade_patch_adaptive.py` (5-3) |
| DDIC `comm_fail_prob=0.0` | Eval-script ≠ training condition | `_phase4_eval.py:33` | This audit |

Both are eval-script vs reference-condition silent mismatches that bias the headline number favorably.

---

## 4. Verdict — which number is correct

**Use `−1.156` (paper_grade)**, not `−1.093` (phase4_eval).

Reason: eval condition must match training condition (`comm_fail_prob=0.1`) for the metric to mean "what the trained policy actually achieves on the scenario it was trained for." Evaluating at `comm_fail_prob=0.0` is testing a counterfactual the policy was never optimized against, and it inflates the headline by 6%.

Adaptive K=10/400 = −1.060 is unaffected (no comm dependence) and remains the correct comparison baseline.

---

## 5. Predraft impact

Files needing patch:
- `quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft.md`
  - Line 6 abstract: `−1.093 vs −3.99` → `−1.156 vs −3.99`
  - Line 76: `(-1.093 cum_rf)` → `(-1.156 cum_rf)`
  - Line 100 Table 1 row: `−1.093` → `−1.156`
  - Line 133 honest assessment: `−1.093 vs −1.060 (3% worse)` → `−1.156 vs −1.060 (9% worse)`
  - Line 141 paper-anchor table: `−1.093` → `−1.156`
  - Line 213: 3-seed mean row → `−1.156`
  - Line 318 honest claim: same 9% worse update
  - Line 338 std-CI section: cross-seed std must be re-derived from new per-seed totals
  - Line 391 conclusion: ratio 1.03 → ~1.09 (DDIC 9% worse on cum_rf)

Win narrative shift:
- Old (predraft): "DDIC loses 3% on cum_rf, 95% CI overlaps adaptive" → marginal-loss / TIED
- New (paper_grade): "DDIC loses 9% on cum_rf, but bootstrap CI [-0.0259, -0.0206] overlaps adaptive [-0.0264, -0.0163]" → still TIED at α=0.05, but the point-estimate gap is bigger

Other metrics from paper_grade summary unaffected:
- max_df_mean: DDIC 0.235 vs adaptive 0.215 (9% worse) — unchanged
- ROCoF mean: DDIC 0.614 vs adaptive 0.676 — unchanged (DDIC wins)
- osc_mean: re-pull from paper_grade JSON (current predraft has 0.103 from phase3_eval_v2)

---

## 6. Recommendation

1. **Adopt paper_grade as the single source of truth** for headline numbers.
2. **Deprecate `_phase4_eval.py`** — annotate it with a deprecation banner pointing to `_eval_paper_grade_andes_one.py`. Don't delete (keeps audit trail).
3. **Patch predraft** with paper_grade numbers across all 9 cited locations (§5).
4. **Re-derive cross-seed std/CI** from paper_grade per-seed totals (−1.191, −1.364, −0.914) → mean −1.156, std 0.184.
5. **Update Table 1, abstract, conclusion, honest claims** consistently.

After patch, predraft narrative becomes:
> "DDIC ties adaptive on cum_rf (−1.156 vs −1.060, bootstrap CI overlaps), wins osc 10%, wins ROCoF 9%, loses max_df 9%. Statistically tied with the best tuned adaptive on the primary frequency-deviation metric."

This is the same qualitative conclusion as the predraft (TIED), with a slightly larger point-estimate gap that does not change statistical significance at n=3.

---

## 7. Open follow-up

- Tier A (n=5) Shared-param: Shared-param 3-seed × 500ep completed 2026-05-04 (see §8 below). Tier A (seeds 45/46) still pending.
- Predraft will need a further pass after Tier A n=5 numbers integrate.

---

## 8. Phase 9 shared-param same-class bug (2026-05-04)

**Same root-cause class** as the `_phase4_eval.py:33` bug documented in §2–3 above.

### 8.1 Bug location

`scenarios/kundur/_phase9_shared_param_sac_full.py:145`:
```python
# BEFORE (buggy):
env = AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.0)

# AFTER (fixed):
env = AndesMultiVSGEnv(random_disturbance=True)  # Use env default comm_fail_prob=0.1 to match training; see audit 2026-05-04
```

Training comm_fail_prob confirmed: `_phase9_shared_param_sac.py:81` — `AndesMultiVSGEnv(random_disturbance=True, comm_fail_prob=0.1)`. [FACT: checked at HEAD 2026-05-04 ~08:00]

### 8.2 Buggy numbers (comm_fail_prob=0.0)

From `results/andes_phase9_shared_seed{42,43,44}_500ep/eval_paper_grade.json` (kept, NOT deleted):

| Seed | cum_rf/ep (comm=0.0) |
|---:|---:|
| 42 | −0.0254 (total −1.270) |
| 43 | −0.0185 (total −0.926) |
| 44 | −0.0174 (total −0.871) |
| **3-seed mean total** | **−1.022** |

These appeared to beat both DDIC (−1.156) and adaptive (−1.060), which would have been a large positive claim — but the comparison was **invalid** (comm=0.0 vs DDIC/adaptive at comm=0.1).

### 8.3 Corrected numbers (comm_fail_prob=0.1)

From `results/andes_phase9_shared_seed{42,43,44}_500ep/eval_paper_grade_v2.json` [FACT: computed 2026-05-04 ~08:30, `_phase9_shared_3seed_reeval.py`, bootstrap seed=7919, n_resample=1000]:

| Seed | cum_rf/ep (comm=0.1) | 50-ep 95 % CI |
|---:|---:|---:|
| 42 | −0.0271 (total −1.356) | [−0.0315, −0.0228] |
| 43 | −0.0185 (total −0.924) | [−0.0226, −0.0150] |
| 44 | −0.0185 (total −0.927) | [−0.0217, −0.0160] |
| **3-seed mean total** | **−1.069** | **[−0.0237, −0.0193]** (150-ep pool) |

3-seed total std (n-1) = 0.248. Aggregate saved: `results/phase9_shared_3seed_reeval_summary.json`.

### 8.4 Impact

Old (buggy) 3-seed mean: −1.022. New (correct) 3-seed mean: −1.069. Direction unchanged (both better than DDIC −1.156 in point estimate), but the margin vs DDIC decreased from 11.5 % to 7.5 %. Verdict: **DECORATIVE_CONFIRMED** (bootstrapped CIs overlap with both DDIC and adaptive; shared-param not statistically distinguishable from either). Predraft §2.6 updated accordingly.

### 8.5 Audit trail

- Buggy eval JSONs: `results/andes_phase9_shared_seed{42,43,44}_500ep/eval_paper_grade.json` — KEPT for audit trail, do not re-run
- Corrected eval JSONs: `results/andes_phase9_shared_seed{42,43,44}_500ep/eval_paper_grade_v2.json`
- Re-eval script: `scenarios/kundur/_phase9_shared_3seed_reeval.py`
- Fixed training script: `scenarios/kundur/_phase9_shared_param_sac_full.py:145`

---

## Files referenced

- `scenarios/kundur/_phase4_eval.py:33` — `comm_fail_prob=0.0` (the original bug)
- `scenarios/kundur/_phase9_shared_param_sac_full.py:145` — same bug, fixed 2026-05-04
- `scenarios/kundur/_eval_paper_grade_andes_one.py:262` — default (correct)
- `scenarios/kundur/train_andes.py:136` — training uses 0.1
- `scenarios/kundur/_phase9_shared_param_sac.py:81` — training uses 0.1
- `env/andes/base_env.py:108,137,437` — COMM_FAIL_PROB=0.1, default fallback, comm_eta sampling
- `results/andes_phase4_eval/summary.json` — old (artifact-prone) numbers
- `results/andes_eval_paper_grade/per_seed_summary.json` — fresh (correct) DDIC numbers
- `results/phase9_shared_3seed_reeval_summary.json` — Phase 9 corrected aggregate

[FACT] All file:line references checked at HEAD on 2026-05-04. §8 added 2026-05-04 ~08:30.
