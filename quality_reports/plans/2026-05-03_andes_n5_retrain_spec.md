# Plan: ANDES Kundur DDIC — Extend n=3 to n=5 (Tier A) / n=10 (Tier B) Retrain Spec

**Date:** 2026-05-03
**Status:** DRAFT
**Owner:** future-work — gated on critic v1 P1-3 disposition
**Source predraft:** `quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_v2.md`
**Trigger:** Critic v1 P1-3 — n=3 95% CI [-1.53, -0.66] is too wide; adaptive baseline -1.060 falls inside.

---

## 1. Background & Motivation

[FACT] Phase 4 ANDES Kundur DDIC was trained with 3 seeds (42, 43, 44) under config `PHI_ABS=0`, `D_FLOOR=1.0`, 500 ep / seed.
- Source dirs: `results/andes_phase4_noPHIabs_seed{42,43,44}/training_log.json` (each 500 ep, `total_steps=25000`, `interrupted=false`).
- Final agent state: `results/harness/kundur/agent_state/agent_state_phase4_seed{42,43,44}_final.json`.

[FACT] Predraft v2 reports: DDIC mean cum_rf = -1.093, std = 0.176 across 3 seeds; t-distribution 95% CI half-width with n=3 uses t(2, 0.025)=4.303, giving CI ≈ [-1.53, -0.66].
[FACT] Best adaptive baseline (K=10/400) reports cum_rf = -1.060, which lies inside the n=3 CI.

[CLAIM] Critic v1 P1-3: with n=3 the CI is uninformative for paper-class statistical claims; "DDIC beats best adaptive on cum_rf" is not supported.
[CLAIM] Goal of this spec: tighten CI half-width to a level where DDIC vs adaptive cum_rf separation (or equivalence) can be defended, OR explicitly accept stat-tie framing.

## 2. Sample Size Analysis

Target: 95% CI half-width < 0.10 (≈ 9% of |mean|).

Formula: `half_width = t(n-1, 0.025) × σ / √n`, assuming σ ≈ 0.176 from current 3 seeds.

| n  | t(n-1, 0.025) | σ / √n  | Half-width |
|----|---------------|---------|------------|
| 3  | 4.303         | 0.1016  | 0.437      |
| 5  | 2.776         | 0.0787  | 0.219      |
| 10 | 2.262         | 0.0557  | 0.126      |
| 20 | 2.093         | 0.0394  | 0.082      |

[CLAIM] Conclusion: n=5 reduces half-width by ~50% vs n=3 but still spans the gap to adaptive (-1.060). n=10 is the smallest n that brings half-width ≤ 0.13. n=20 is required for half-width < 0.10.

[CLAIM] Caveat: assumes σ stays ≈ 0.176 as n grows. If new seeds raise σ, n=10 may also remain inconclusive — see §10 risk.

## 3. Proposed Experiments — Two Tiers

Same config as Phase 4 in all tiers: `PHI_ABS=0`, `D_FLOOR=1.0`, 500 ep / seed, ANDES backend, `random_disturbance=True`, `comm_fail_prob=0.0`. Driver: `scenarios/kundur/train_andes.py --seed <S>`.

### Tier A: n=5 minimum
- Existing: seeds 42, 43, 44.
- New: seeds 45, 46.
- Total new training: 2 seeds × 500 ep.

### Tier B: n=10 (only if Tier A inconclusive)
- Existing after Tier A: seeds 42–46.
- New: seeds 47, 48, 49, 50, 51.
- Total new training: 5 seeds × 500 ep.

[CLAIM] Numbering uses contiguous integers to keep `--seed` reproducibility convention from `train_andes.py:43,63-66` (`np.random.seed`, `torch.manual_seed`).

## 4. Wall Budget & Hardware

[FACT] Phase 4 training was run on WSL with `~/andes_venv` (per `_eval_paper_grade_andes.py:7-10` invocation), parallel-3 across seeds 42/43/44.
[CLAIM] Predraft v2 quotes ~6 GPU-hours total for 3 seeds. Implied: ~6200 s wall / seed at parallel-3 (CPU contention reduces per-seed throughput).

Estimates (extrapolated from Phase 4 actuals; ANDES TDS is CPU-bound, not GPU-bound):

| Plan | Concurrency | New seeds | Wall |
|------|-------------|-----------|------|
| Tier A | parallel-2 (alongside 3 idle slots) | 2 | ~110-130 min |
| Tier A | parallel-5 (full saturation) | 2 | ~110-130 min (no benefit, free cores) |
| Tier B | parallel-5 | 5 | ~3-4 h |
| Tier B | parallel-10 (heavy contention) | 5 | indeterminate; not recommended |

Recommended: Tier A → parallel-2 standalone; Tier B → 5 sequential or parallel-5 if CPU/RAM allow.

## 5. Convergence Criteria (per seed)

Each new seed must satisfy ALL of:
1. `total_rewards[-1] / total_rewards[0]` ratio improvement: |last 10-ep mean| < 0.2 × |first 10-ep mean| (equivalent to >5× reward improvement).
2. Zero `interrupted=true` flag in `training_log.json`.
3. ANDES TDS failures = 0 across the 500-ep run (env raises no `tds.busted` exceptions).
4. Action stability: action std over last 30 ep > 0.05 in both H and D dims (not collapsed to deterministic).

If any criterion fails → replace seed, do not pad. (See §10 risk.)

## 6. Output Artifacts (per new seed)

For seed N ∈ {45, 46} (Tier A) or {47..51} (Tier B):

1. `results/andes_phase4_noPHIabs_seed{N}/training_log.json` — total_rewards (matches Phase 4 schema; see seed42 file as template).
2. `results/andes_phase4_noPHIabs_seed{N}/agent_*_final.pt` and `agent_*_best.pt` (4 agents × 2 ckpts).
3. Run probe: `agent_state_phase4ext_seed{N}_final.json` under `results/harness/kundur/agent_state/` (use existing probe driver matching `agent_state_phase4_seed42_final.json` schema).
4. Run paper §IV-C eval: invoke `scenarios/kundur/_eval_paper_grade_andes.py` with the seed's `_best.pt` checkpoints; output to `results/andes_eval_paper_grade/seed{N}/{ddic,nocontrol,adaptive}.json` and aggregated `summary.json`.

[FACT] Eval driver constants: 50 fixed test seeds (`FIXED_TEST_SEEDS = [20000+i for i in range(50)]`), see `scenarios/kundur/_phase4_eval.py:27`.

## 7. Aggregate Analysis (after Tier A complete)

Steps:
1. Load `summary.json` per seed in {42..46}, extract per-method `cum_rf_global_total / 50`, `max_df`, `osc`, `fail_rate`.
2. Compute n=5: mean ± std (sample), 95% CI via t(4, 0.025)=2.776.
3. Compute bootstrap CI (1000 resamples, percentile method) for `cum_rf_global` per method using `evaluation.metrics._bootstrap_ci` (already imported by `_eval_paper_grade_andes.py:39`).
4. Update predraft Table 1: replace n=3 row with n=5 mean / std / t-CI / bootstrap-CI.
5. Replace abstract "3 training seeds" → "5 training seeds" and update CI quote.

## 8. Decision Gates

After Tier A:
- **Gate A1** — n=5 95% CI for DDIC `cum_rf_global` does NOT contain best-adaptive value (-1.060): claim "DDIC > best adaptive on cum_rf" is defensible → submit predraft v3, stop.
- **Gate A2** — n=5 CI still contains -1.060 but bootstrap separation p < 0.05 on osc and `max_df` looks unchanged: ambiguous → proceed to Tier B.
- **Gate A3** — n=5 std grows materially (e.g., > 0.25), CI widens or stays similar: proceed to Tier B; flag "high cross-seed dispersion" in §10 risk log.

After Tier B (if reached):
- **Gate B1** — n=10 95% CI excludes -1.060: claim defensible.
- **Gate B2** — n=10 CI still overlaps: accept "DDIC stat-tied with best adaptive on cum_rf, wins on osc (already 10% better, n=3)" framing in revised abstract.

## 9. Effort Allocation

| Phase | Activity | Wall |
|-------|----------|------|
| Tier A | Train seeds 45, 46 | 2-3 h |
| Tier A | Probe + paper-grade eval (2 seeds) | 30 min |
| Tier A | Aggregate + predraft update | 20 min |
| Tier A total | | ~3-5 h |
| Tier B | Train seeds 47-51 | 4-6 h |
| Tier B | Probe + eval | 60 min |
| Tier B | Aggregate + predraft update | 20 min |
| Tier B total | | ~6-8 h |

[CLAIM] Wall depends on whether parallel work (Simulink, single-agent baseline) is contending for CPU.

## 10. Risks

1. **Cross-seed dispersion stays at 16% (= current σ/|mean|)**: CI tightens only by √n (n=3→5: factor 1.29; n=3→10: factor 1.83). Already reflected in §2 table.
2. **σ grows with new seeds**: possible if seed 45/46 sample new behavior modes (e.g., agent-1 dominance flips). If σ doubles, n=10 half-width ≈ 0.25 → still inconclusive. Mitigation: report dispersion explicitly; do not auto-extrapolate to "DDIC superior".
3. **A new seed diverges or hits TDS failure**: replace, do not pad — n must be honest. Track replacements in predraft footnote.
4. **ANDES + WSL undocumented seed sensitivity**: `train_andes.py` seeds numpy + torch (lines 63-66) but ANDES internal RNG may not be seeded; per-seed TDS solver paths could be non-deterministic. Mitigation: rerun any seed twice if borderline; if non-determinism > 1% of cum_rf, pause and audit ANDES seeding.
5. **CPU contention with parallel work**: if Simulink training runs simultaneously, seed wall extends; coordinate scheduling.
6. **Best-adaptive value -1.060 itself based on single eval run**: if adaptive evaluation is not also reported with bootstrap CI, gate logic in §8 is asymmetric. Mitigation: include adaptive bootstrap CI from the eval driver (same `_bootstrap_ci` import) when reporting Tier A/B results.

## 11. Out-of-Scope

- Different `PHI_ABS` configurations (separate experiment; PHI sweep currently locked under PAPER-ANCHOR rule, see CLAUDE.md §🚨).
- Architecture / hidden-size changes (Phase 8/9 territory).
- Single-agent baseline (already running parallel — see `2026-05-03_andes_effective_agent_optimization.md`).
- Simulink-side seed extension (this spec is ANDES-only).
- Refactor of `_eval_paper_grade_andes.py` itself.

## 12. References

- Source files (read for budget and config):
  - `scenarios/kundur/train_andes.py` (seed plumbing lines 43, 48-49, 63-66, 137).
  - `scenarios/kundur/_eval_paper_grade_andes.py` (paper-grade eval driver, constants lines 43-50).
  - `scenarios/kundur/_phase4_eval.py` (FIXED_TEST_SEEDS, line 27; paper-§IV-C method comparison).
  - `results/andes_phase4_noPHIabs_seed42/training_log.json` (Phase 4 actual run, 500 ep, total_steps=25000).
  - `results/harness/kundur/agent_state/agent_state_phase4_seed42_final.json` (probe output schema reference).
- Predraft to update: `quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_v2.md`.
- Sibling plan: `quality_reports/plans/2026-05-03_andes_effective_agent_optimization.md`.
- Behavior rule: `CLAUDE.md §🚨 PAPER-ANCHOR HARD RULE` — n=5 results are not "paper claims" until G1-G6 also pass; this spec only addresses statistical rigor (P1-3), not signal validity.

---

**Status semantics:** DRAFT until critic v1 P1-3 disposition decided. ON-HOLD if Phase 4 paper-anchor signal validity gates remain failing — there is no value in tightening CI on a metric whose physical signal is broken (see CLAUDE.md). Promote to APPROVED only when (a) critic accepts P1-3 plan, AND (b) signal-layer probes validate that ANDES Kundur cum_rf is paper-meaningful.
