# ANDES DDIC — Hyperparameter Sensitivity Spec (1D Log-Scale Perturbation)

**Date**: 2026-05-04
**Branch**: main (HEAD ≈ 95d7e84 at plan creation)
**Status**: DRAFT (pre-registration; gates fixed before execution)
**Scope**: Pre-register a low-cost, robustness-oriented hyperparameter
sensitivity analysis for the ANDES Kundur 4-ESS DDIC reproduction. The
goal is **not** to find the global-optimal config; the goal is to verify
that current published numbers (cum-$r_f$ = −1.186 at PHI_F=10000,
PHI_D=0.02, action ∈ [−10, +30]) are **insensitive within a local
log-scale neighborhood (±2× to ±3× per axis)**, with paper-original
anchors tested as separate data points outside the neighborhood.

**Predecessors**:
- `quality_reports/plans/2026-05-03_andes_n5_retrain_spec.md` (Tier A
  n=5 spec)
- `quality_reports/audits/2026-05-04_andes_tier_a_n5_verdict.md` (n=5
  result + gate A3)
- `quality_reports/audits/2026-05-04_andes_ddic_eval_discrepancy_verdict.md`
  (comm_fail_prob bug audit)

**Triggers from**: methodology gap discussion 2026-05-04 — current paper
§I.B "Project Deviations" lists PHI_F/PHI_D/action-range values without
sensitivity evidence; reviewers will ask "why these exact values".

---

## 1. Hypotheses + Falsification Gates

| ID | Hypothesis | Gate (pre-registered) | If FAIL | Wave |
|---|---|---|---|---|
| H_robust_PHI_F | DDIC cum-$r_f$ at PHI_F ∈ {3000, 10000, 30000} (±3× neighborhood) varies less than the n=5 cross-seed std (0.265) | std(cum_rf across the 3 PHI_F points) < 0.265 | Paper §V claim becomes "robust within ±3× on PHI_F"; if FAIL claim is "fragile in PHI_F dimension" | **W1** (3 points complete after wave 1) |
| H_robust_PHI_D | Same for PHI_D ∈ {0.006, 0.02, 0.06} (±3× neighborhood) | std < 0.265 | same | W1+W2 (2 points after W1, +d_low in W2) |
| H_robust_action | Same for action ∈ {[−5,15], [−10,30], [−20,60]} (±2× neighborhood) | std < 0.265 | same | W1+W2 (2 points after W1, +a_low in W2) |
| H_anchor_paper_F | Paper-original PHI_F=100 (with PHI_D=0.02 kept) trains in ANDES without TDS divergence | training completes 100 ep without TDS_failed > 50 % of episodes | If FAIL → expected (Phase 1 verdict precedent); reported as "paper-original PHI_F is incompatible with ANDES backend" | **W0** (reuse `phase2_pdf002` 50ep) |
| H_anchor_paper_action | Paper-original action range ΔH ∈ [−100, +300] (i.e., ΔM ∈ [−200, +600]) trains without TDS divergence | same | same | **W0** (reuse `phase11_ddic_wide_seed42` 77ep) |
| H_decorative_robust | Shared-parameter SAC at the representative point still matches DDIC within 10 % | reuse Phase 9 data at PHI_F=10000, PHI_D=0.02; if representative point ≠ this, retrain | If FAIL → "decoration claim is hyperparameter-fragile" | **W0** (reuse `phase9_shared_seed{42..44}_500ep`) |

All gates above are **pre-registered**: the rejection / acceptance
logic is fixed before any data is collected. No post-hoc renegotiation.

---

## 2. Health Metrics (precise definitions)

All metrics computed on the **training trace** (no test-set leakage).
Window: episodes 50–100 (last half of training, after warmup).

| Metric | Formula | Threshold |
|---|---|---|
| `D_floor_hit_rate` | fraction of (agent, step) pairs in window where $|D_i - D_{\text{floor}}| < 0.02$ | ACCEPT < 50 %, IDEAL < 20 % |
| `rf_share` | mean over window of $|r_f| / (|r_f| + |r_h| + |r_d| + |r_{\text{abs}}| + \epsilon)$, $\epsilon = 10^{-9}$. Absolute values used because reward components are negative; ratio measures gradient-magnitude share, not signed share | ACCEPT ∈ [5 %, 50 %], IDEAL ∈ [10 %, 40 %] |
| `action_saturation` | fraction of (agent, step, dim) tuples in window where $|a_i^{(j)} - 1.0| < 0.05$ or $|a_i^{(j)} + 1.0| < 0.05$ | ACCEPT < 70 %, IDEAL < 50 % |
| `tds_divergence_rate` | fraction of episodes in window with `info["tds_failed"] = True` | ACCEPT < 5 %, IDEAL = 0 % |
| `convergence_drift` | $\overline{\text{cum\_rf}}_{90:100} - \overline{\text{cum\_rf}}_{50:60}$ where bar denotes mean over the episode window. Reward closer to 0 is better, so improving = positive drift. Use cum_rf (not total reward) to avoid action-penalty contamination | ACCEPT > 0 (improving toward 0), no upper bound |

**Compute source**: `results/andes_hparam_sweep/<config_id>/training_log.json`
+ `monitor_data.csv`. Helper script
`scripts/compute_health_metrics.py` (TO BE WRITTEN as part of execution).

A configuration is **rejected** if any ACCEPT threshold fails. Among
accepted, the **representative point** is selected by §4 below.

---

## 3. Stage 1 — 1D Local Log-Scale Perturbation Grid (±2× to ±3× per axis)

**12 configurations** total (9 perturbation + 3 paper anchors). Each
trained 1 seed × 100 episodes. Seed = 42 fixed (single seed; this is a
screening sweep, not a definitive run).

| ID | PHI_F | PHI_D | Action range | Notes |
|---|---|---|---|---|
| `f_low`     | 3000  | 0.02  | [−10, 30] | PHI_F 0.3× baseline (−3.3×) |
| `f_mid`     | 10000 | 0.02  | [−10, 30] | **current point** |
| `f_high`    | 30000 | 0.02  | [−10, 30] | PHI_F +3× |
| `f_anchor`  | 100   | 0.02  | [−10, 30] | paper PHI_F (PHI_D kept project) |
| `d_low`     | 10000 | 0.006 | [−10, 30] | PHI_D −3× |
| `d_mid`     | 10000 | 0.02  | [−10, 30] | = `f_mid` (skip duplicate; reuse training) |
| `d_high`    | 10000 | 0.06  | [−10, 30] | PHI_D +3× |
| `d_anchor`  | 10000 | 1.0   | [−10, 30] | paper PHI_D (PHI_F kept project) |
| `a_low`     | 10000 | 0.02  | [−5, 15]  | action −2× |
| `a_mid`     | 10000 | 0.02  | [−10, 30] | = `f_mid` |
| `a_high`    | 10000 | 0.02  | [−20, 60] | action +2× |
| `a_anchor`  | 10000 | 0.02  | [−200, 600] | paper-original ΔM (under M=2H mapping ΔH ∈ [−100, +300]) |

**Net unique trainings**: 10 (drop 2 duplicates of `f_mid`).
**Wall budget**: 100 ep ≈ 22 min/seed (Tier A measurement, scaled);
10 trainings × 22 min ÷ 4 parallel = **~55 min wall**.

**Output dirs**: `results/andes_hparam_sweep/<id>_seed42/`.

**CLI requirement**: `train_andes.py` must accept
`--phi-f`, `--phi-d`, `--dm-min`, `--dm-max`, `--dd-min`, `--dd-max`
flags. **Pre-execution check**: verify or add these flags before Stage 1
launches.

---

## 3.5. Reuse Matrix (existing runs that satisfy spec configs)

Pre-flight inventory of `results/` finds 3 of 10 unique configs already
have data on disk. Reuse rules pre-registered before any new training.

| Spec ID | Existing run | Episodes | Match evidence | Reuse status |
|---|---|---|---|---|
| `f_mid` | `andes_phase4_noPHIabs_seed{42..46}/` | 5 × 500ep | Phase 4 canonical baseline (CLAUDE.md §Anti-Retry; predraft §3.1) — PHI_F=10000, PHI_D=0.02, action [-10,30] | **REUSE in full** — health metrics computed on ep[50:100] window from each of 5 seeds; representative-point assertion (§4) uses 5-seed median |
| `f_anchor` | `andes_phase2_pdf002/` | 50ep | Reverse-engineered from `per_step.jsonl[0]`: `r_f_weighted_total / sum(r_f_raw_per_agent) ≈ 100`; `r_d_weighted_total / r_d_raw ≈ 0.02`. Confirms PHI_F=100, PHI_D=0.02 | **REUSE for anchor gate only** — 50ep < 100ep neighborhood spec; sufficient to evaluate H_anchor_paper_F (TDS_failed > 50% gate) but cum_rf comparison to neighborhood is invalid (caveat must be in audit) |
| `a_anchor` | `andes_phase11_ddic_wide_seed42/` | 77/500ep (early-stopped on TDS divergence) | `quality_reports/audits/2026-05-04_phase11_wide_range_pilot_plan.md` confirms `action_scale=20.0` → DM ∈ [-200,+600], DD ∈ [-200,+600] = spec a_anchor; log shows continuous "Time step reduced to zero / Convergence is not likely" → TDS divergence pattern matches H_anchor_paper_action FAIL prediction | **REUSE in full** — gate already satisfied; no retrain needed |

**Net new training**: 7 unique configs × 1 seed × 100ep instead of
spec §3 original 10. Wall budget: 7 × 22min ÷ 4-parallel ≈ **40 min**
(was 55 min in §3).

**Reuse caveats** (must be cited in audit):

- `f_mid` health metric window = ep[50:100] of 500ep run is the **last
  half of the first 100ep**, not "the last half of training". This is
  intentional — it makes `f_mid` health directly comparable to the
  100ep neighborhood points. Separate ep[450:500] window may be
  reported as additional evidence of late-training behavior but is
  **not** the gate input.
- `f_anchor` 50ep < 100ep means `convergence_drift` is not measurable on
  the 50–60 vs 90–100 window; report as `N/A` with explanation.
- `a_anchor` 77ep early-stop is itself the gate evidence; do not extrapolate.

---

## 4. Representative Point Selection

**Criterion (pre-registered, in priority order)**:

1. The representative point is `f_mid` = (PHI_F=10000, PHI_D=0.02,
   action [−10, 30]) **provided it passes all ACCEPT health thresholds
   in §2**. If yes, no new training is needed for Stage 3 — reuse the
   existing 5-seed × 500-ep results from
   `results/andes_phase4_noPHIabs_seed{42…46}/`.

2. If `f_mid` fails any threshold, fall back to the median-health
   configuration among accepted configs. "Median health" = lowest
   `|rf_share − 25 %|` among accepted, ties broken by lowest
   `D_floor_hit_rate`.

3. If fallback is needed, retrain at the new representative point
   (n=5 × 500 ep) and rerun Phase 9 shared-param + Phase 4 adaptive
   K-grid at the new point. Cost: ~6–8 h wall.

**Rationale for not selecting the optimum**: this is a null-result
paper. Selecting the optimum config invites cherry-picking critique.
Selecting a representative point preserves the existing data lineage
and lets the §V claim be "results are robust at a typical-behavior
config", which is the actual scientific content.

---

## 5. Stage 3 — Reuse Plan + Neighborhood Robustness Verdict

**No new full training expected** (assuming `f_mid` is representative).

| Method | Source (existing) | $n$ | cum_rf_total |
|---|---|---|---|
| DDIC (Phase 4) | `results/andes_eval_paper_grade/n5_aggregate.json` | 5 | −1.186 |
| Shared-param SAC (Phase 9) | `results/phase9_shared_3seed_reeval_summary.json` | 3 | −1.069 |
| Adaptive K=10/400 | `results/andes_eval_paper_grade/per_seed_summary.json` | 1 (50 eps) | −1.060 |

**Neighborhood robustness verdict**: compute std of cum-$r_f$ totals
across the 3 perturbation points per axis (Stage 1 outputs).

| Axis | Neighborhood width | std target | If std < 0.265 | If std ≥ 0.265 |
|---|---|---|---|---|
| PHI_F (3 points) | ±3× | < 0.265 | "robust within ±3× on PHI_F" | "fragile in PHI_F dimension; reported sensitivity" |
| PHI_D (3 points) | ±3× | < 0.265 | "robust within ±3× on PHI_D" | same |
| action range (3 points) | ±2× | < 0.265 | "robust within ±2× on action range" | same |

The 0.265 threshold is the existing n=5 cross-seed std; passing means
hyperparameter perturbation **within the local neighborhood** produces
less variance than seed perturbation, i.e., the choice does not
materially affect the result inside that range. This is a local
sensitivity claim, not a global-decade-robustness claim.

**Anchor verdicts** (separate from robustness): each anchor reports
training success / failure (TDS rate, convergence drift) and final
cum-$r_f$ if completed. Anchor failures are reported as evidence that
paper-original parameters do not transfer; anchor successes are
unexpected and warrant follow-up.

---

## 6. Paper §V Insertion Plan

**Target location**: new subsection §IV.E "Hyperparameter Sensitivity"
after §IV.D (current root-cause synthesis), before §V "Honest Claims".

**Content** (~3/4 page, ~30 lines text + 1 table + 1 figure):

- One paragraph: methodology (1D local log-scale perturbation over ±2×
  to ±3× neighborhood, screening protocol, representative point
  selection rationale, anchor purpose; explicitly states this is local
  sensitivity, not global decade robustness).
- Table: 10–12 configs × {PHI_F, PHI_D, action, health-pass, cum_rf}.
- Figure: 1D sweep, x = log(PHI_F) and log(PHI_D) and action-width on
  parallel sub-axes, y = cum_rf, error bars from training std (n=1 →
  no error bars; report point estimates with caveat).
- One paragraph: verdict per axis (robust / fragile), neighborhood std
  vs cross-seed std comparison, anchor outcomes.
- One sentence in §V "Honest Claims" updated: "claim N+1: results are
  locally robust within ±3× on PHI_F and PHI_D and ±2× on action range
  (neighborhood test, not full-decade); paper-original anchors outside
  this neighborhood fail as expected (TDS divergence)".

**Output audit doc**: 
`quality_reports/audits/2026-05-XX_andes_hparam_sensitivity_verdict.md`
— produced as part of execution, cited from Paper §IV.E.

---

## 7. Risks + Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| 100 ep too short to detect convergence quality | medium | Health metrics use windows 50–60 vs 90–100; trajectory analysis (Phase 4 verdict) shows lock by ep 100 — adequate signal |
| `f_mid` fails health threshold (forcing fallback) | low | Existing 500-ep training for seeds 42–46 already passes every threshold per §III.A audit; failure at 100 ep would contradict that — would itself be a valuable finding |
| Anchor configs diverge (TDS_failed) | high (expected) | Treated as data point; bound TDS time so divergence doesn't waste budget. Set `--tds-fail-max 25` to abort runs with > 25 % failed episodes |
| 1D perturbation misses (PHI_F × PHI_D) interaction | medium | Pre-register: if PHI_F or PHI_D axis fails robustness, do a targeted 2D probe at the failing region (~3 h additional) |
| Single seed (s=42) is unrepresentative | medium | Acknowledged; this is a screening sweep, not definitive. The representative point gets full n=5 × 500 ep treatment via reuse |
| CLI flags `--phi-f` etc. don't exist in `train_andes.py` | high (confirmed missing 2026-05-04 pre-flight) | Add via class-attr monkey-patch in `train_andes.py` before env construction; do **not** modify `env/andes/base_env.py` (minimum diff). Verify injection by reverse-engineering PHI_F from `per_step.jsonl[0]` after first ep |
| `f_anchor` reused from 50ep `phase2_pdf002` — shorter than 100ep neighborhood points | medium | Use only for H_anchor_paper_F gate (TDS-divergence evidence); mark `convergence_drift` and cum_rf trend comparison as N/A in audit. If gate ambiguous at 50ep (TDS rate borderline), retrain anchor at 100ep (cost: +22min wall) |
| Wave-1 mid-flight kill leaves orphaned partial training data | low | Each wave-1 run writes to its own `results/andes_hparam_sweep/<id>_seed42/` dir; orphaned runs are harmless if killed (training_log.json records `interrupted=True` + last_ep). Audit treats `<30ep` early-killed runs as N/A, not FAIL |

---

## 8. File References

**Inputs**:
- `scenarios/kundur/train_andes.py` (training; needs CLI flag check)
- `scenarios/kundur/_eval_paper_grade_andes_one.py` (eval; not used in
  Stage 1 screening, only for representative-point full eval)
- `env/andes/base_env.py` (PHI_F, PHI_D, DM_MIN/MAX, DD_MIN/MAX
  constants — must be CLI-overridable)
- `config.py` (default hyperparameters)

**Outputs**:
- `results/andes_hparam_sweep/<id>_seed42/training_log.json`
  (per-config training trace)
- `results/andes_hparam_sweep/health_summary.json` (aggregate health
  metrics, all configs)
- `results/andes_hparam_sweep/figure.png` (1D sweep visualization)
- `quality_reports/audits/2026-05-XX_andes_hparam_sensitivity_verdict.md`

**Helper scripts to write**:
- `scripts/compute_health_metrics.py` (parse training_log + monitor_data,
  compute the 5 metrics in §2, emit JSON)
- `scripts/plot_hparam_sweep.py` (1D sweep figure)
- `scenarios/kundur/_hparam_sweep_aggregate.py` (cross-config aggregate
  + verdict against pre-registered gates)

---

## 9. Execution Order (wave-based, with early-kill gates)

**Strategy**: Stage 1 split into 2 waves. Wave 1 = 4 highest-information
configs in parallel; verdict on each axis decides wave 2 scope.
Wave 0 reuses existing data (§3.5) without new training.

### Wave 0 — Reuse existing data (0 h wall, 0 new training)

- `f_mid` ← `andes_phase4_noPHIabs_seed{42..46}/` (n=5 × 500ep)
- `f_anchor` ← `andes_phase2_pdf002/` (50ep, anchor gate only)
- `a_anchor` ← `andes_phase11_ddic_wide_seed42/` (77ep TDS-divergent)

### Wave 1 — Pre-flight + 4-way parallel (2 h wall)

1. **Pre-flight (15 min)**
   - Read `scenarios/kundur/train_andes.py`. Add 6 CLI flags
     `--phi-f`, `--phi-d`, `--dm-min`, `--dm-max`, `--dd-min`, `--dd-max`
     via **class-attr monkey-patch on `AndesMultiVSGEnv`** before env
     construction (no edit to `env/andes/base_env.py`). TDS-rate early
     stop deferred to wave 2 if needed (wave 1 uses manual monitor
     check at ep 30).
   - Write `scripts/compute_health_metrics.py` skeleton.

2. **Wave 1 launch (4 background processes, ~40 min wall)**

   | Run | PHI_F | PHI_D | Action | Save dir | Information goal |
   |---|---|---|---|---|---|
   | `f_low` | 3000 | 0.02 | [-10,30] | `results/andes_hparam_sweep/f_low_seed42/` | F-axis lower neighborhood |
   | `f_high` | 30000 | 0.02 | [-10,30] | `results/andes_hparam_sweep/f_high_seed42/` | F-axis upper neighborhood |
   | `d_high` | 10000 | 0.06 | [-10,30] | `results/andes_hparam_sweep/d_high_seed42/` | D-axis upper neighborhood |
   | `a_high` | 10000 | 0.02 | [-20,60] | `results/andes_hparam_sweep/a_high_seed42/` | action upper neighborhood |

   All 1 seed × 100ep × `comm_fail_prob=0.1`. Manual check at ep 30
   (`per_step.jsonl[ep=29]` reverse-engineer PHI_F to confirm injection).

3. **Wave 1 verdict (15 min, after all 4 finish or are killed)**
   - Run `compute_health_metrics.py` over 4 wave-1 dirs + reuse 3.
   - Compute F-axis std (3 points: f_low / f_mid / f_high).
   - Compute partial D-axis (2 points: f_mid / d_high).
   - Compute partial action-axis (2 points: f_mid / a_high).

### Wave 2 — Conditional, decided by wave 1 verdict (0–2.5 h wall)

Pre-registered decision tree:

| Wave 1 observation | Wave 2 action | Cost |
|---|---|---|
| F-axis std < 0.265 **AND** d_high health PASS **AND** a_high health PASS | Run `d_low` + `a_low` to complete D and action axis verdicts | 2 × 22min ÷ 2-parallel = ~25min wall |
| F-axis std ≥ 0.265 (F fragile) | Skip d_low/a_low; run targeted 2D probe (PHI_F × PHI_D, 4 corners) instead | ~3 h wall |
| `d_high` or `a_high` health FAIL severely (TDS > 25% **OR** D_floor > 70%) | Run **opposite-side** point on the failed axis (`d_low` if d_high failed, `a_low` if a_high failed) to test asymmetry | 1 × 22min = ~25min wall |
| All 4 wave-1 runs early-TDS-divergent (<30ep) | **STOP, do not run wave 2.** Investigate monkey-patch injection failure | 0 |
| `d_anchor` (PHI_D=1.0) needed for paper-anchor coverage | Run after wave 2 (independent of robustness verdicts) | 1 × 22min = ~25min wall |

### Wave 3 — Verdict + paper insertion + ship (2 h wall)

3. **Representative point assertion (5 min)**
   - Per §4, expect `f_mid`. Document selection in audit.

4. **Stage 3 reuse + final verdict (30 min)**
   - Pull existing DDIC / shared / adaptive numbers.
   - Apply pre-registered gates (§1) on assembled axis data.
   - Write `quality_reports/audits/2026-05-XX_andes_hparam_sensitivity_verdict.md`.

5. **Paper §IV.E insertion (1 h)**
   - Edit `paper/main.tex` per §6.
   - Recompile main.pdf.
   - Verify `\Cref` cross-references resolve.

6. **Commit + ship (15 min)**
   - Atomic commit: hparam sweep results + audit + paper revision.

**Total wall time**: ~3–6 h depending on wave 2 branch
(40 min wave 1 + 25 min – 3 h wave 2 + 2 h wave 3).
Best case (F robust, single-side asymmetry): ~3 h.
Worst case (F fragile → 2D probe): ~6 h.

---

## 10. Success Criteria (Plan-Level)

- All 10 unique configs trained without infrastructure errors (or
  anchors fail gracefully with documented `tds_failed > 25 %` flag);
  the 2 mid-point duplicates (`d_mid`, `a_mid` = `f_mid`) are
  explicitly reused, not retrained.
- Each pre-registered gate (§1) has a clear PASS / FAIL verdict in the
  audit.
- Paper §IV.E added with table + figure + verdict per axis.
- main.pdf compiles clean.
- One atomic commit on `main` branch.

If any of these fail, the plan is incomplete and must be revised before
shipping.

---

*End of 2026-05-04 ANDES hparam sensitivity spec. Pre-registration
finalized; gates frozen at this revision.*
