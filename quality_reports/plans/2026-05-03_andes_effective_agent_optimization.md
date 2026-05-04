# ANDES Effective-Agent Optimization Plan

**Date**: 2026-05-03
**Status**: DRAFT
**Branch**: main (HEAD = d044fa6)
**Predecessor**: `quality_reports/audits/2026-05-03_andes_dfloor_seed_sweep_verdict.md`
**Stance**: Paper as REFERENCE, not BASELINE. Optimize for effective agent; cite paper as one data point.

---

## Goal

Train an ANDES Kundur 4-agent SAC controller that:
1. **Outperforms no-control baseline** on cum-r_f over 50 random test episodes
2. **Matches or beats fixed-adaptive baseline** [25] Fu et al.
3. **Is reproducible across ≥3 seeds** (mean ± std reported)
4. **Lands within same order of magnitude as paper -8.04** (not exact, project deviations documented)

**Non-goals**: exact paper number reproduction; mechanical paper formula adoption; resolving paper Q-A/Q-D ambiguities.

---

## Phase 1 — Diagnose (no code changes, no reward edits)

**Owner**: this session
**Wall**: ~1.5 h (1 probe run + analysis)
**Output**: diagnostic report identifying TRUE bottleneck (not assumed one)

### 1.1 Add measurement hooks (read-only logging)

Modify `env/andes/base_env.py::_compute_rewards` to also return raw signal magnitudes
(no behavior change, only `info` dict gets richer):
- `info["r_f_raw"]` = `(Δω_i - ω̄)²` (un-weighted, Hz²)
- `info["r_d_raw"]` = `(ΔD_avg)²` (un-weighted)
- `info["r_h_raw"]` = `(ΔH_avg)²`
- `info["d_omega_local"]` = local sync error per agent
- `info["d_omega_global"]` = global frequency deviation

Modify `agents/sac.py::update` to log alpha:
- `loss_info["alpha"]` already exists; ensure it's surfaced in monitor CSV

### 1.2 Run 1 seed × 50 ep with extended logging

```
python3 scenarios/kundur/train_andes.py --episodes 50 --seed 42 \
    --save-dir results/andes_phase1_probe --log-interval 10
```

### 1.3 Build diagnostic script

`scenarios/kundur/_phase1_signal_analyzer.py`:
- Per-ep histogram: `r_f_raw` vs `r_d_raw` magnitudes
- Time series: per-step Δω decay after disturbance — measure τ
- α evolution: does it collapse < 0.05?
- Per-agent action[0] (ΔM) vs action[1] (ΔD) commitment — which dim does each agent over-rely on?

### 1.4 Decision tree (filled by Phase 1 evidence)

| Observation | Likely root cause | Phase 2 action |
|---|---|---|
| `r_f_raw` per-step ≈ 1e-4 (Hz²) | Hz unit + tight sync | TBD: re-weight or rescale obs |
| `r_f_raw` per-step ≈ 1e-1, but PHI_F·r_f_raw still small | weight imbalance | Tune PHI_F up |
| τ (Δω decay) < 0.5s | Network too tight, sync auto-resolves | obs/reward redesign needed |
| α collapses < 0.05 by ep 30 | Entropy bonus failing | Add α_min floor |
| One agent dim 1 (ΔD) saturates, dim 0 idle | Network/buffer imbalance | Reduce N_EPOCH or hidden size |

---

## Phase 2 — Targeted fix (decided POST-Phase-1)

**Owner**: this session, after Phase 1 verdict
**Wall**: ~½ day (1-2 code changes + smoke)
**Output**: 1 verified fix addressing Phase 1 root cause

Plan placeholder — populated after Phase 1 diagnostic. NO speculative fixes here.

Allowed change classes:
- Reward weight rebalance (PHI_F, PHI_H, PHI_D)
- α floor / entropy schedule
- Network arch (hidden_size, depth)
- Buffer/update schedule (N_EPOCH, batch)
- Reward formula additions IF Phase 1 shows fundamental signal weakness

NOT allowed in Phase 2:
- Action range changes (separate B1 probe needed)
- Mechanical "match paper" edits without evidence
- New reward terms beyond what Phase 1 motivates

---

## Phase 3 — Effective-agent run + 3-way comparison

**Owner**: this session, after Phase 2
**Wall**: ~1 day (3 seeds × 500 ep ≈ 5 h, plus baselines)
**Output**: paper-comparable evaluation with multi-seed statistics

### 3.1 Implement no-control baseline

`scenarios/kundur/_eval_nocontrol.py`:
- Load env with H, D fixed at M0=20, D0=4
- Run 50 random test episodes
- Compute global cum-r_f per paper §8.2 formula:
  $-\sum_t \sum_i (f_{i,t} - \bar f_t)^2$
- Report total

### 3.2 Implement fixed-adaptive baseline [25]

`scenarios/kundur/_eval_fixed_adaptive.py`:
- Implement Fu et al. 2022 adaptive virtual inertia formula (paper [25])
  - Brief: H(t) = H0 · (1 + k_H · |Δω̇|), D(t) = D0 · (1 + k_D · |Δω|)
- Same 50 test episodes
- Report total cum-r_f

### 3.3 DDIC final training

Best Phase 2 config × 500 ep × 3 seeds (42, 43, 44):
- Save final policies
- Run 50 test episodes per seed
- Report per-seed cum-r_f + mean ± std

### 3.4 Comparison report

`quality_reports/replications/2026-05-03_andes_effective_agent_3way.md`:
- Table: no-control / fixed-adaptive / DDIC (3-seed mean ± std) / paper -8.04 reference
- Per-episode breakdown for 3 representative episodes (load step 1 / load step 2 / random)
- Documented deviations: PHI_ABS, action range, H_unit Q-A, etc.

---

## What this plan does NOT cover

| Out of scope | Reason |
|---|---|
| Action range expansion to [-100, +300] | Need separate B1 ladder probe; can't predict floor clip behavior on ANDES vs Simulink |
| Resolving Q-A H unit | Paper-level ambiguity; not solvable by experiment |
| 100/50 fixed scenario list | Paper Q-C unresolved; random sampling acceptable for now |
| NE39 ANDES path | Out of scope; Kundur only |
| Simulink path | Active main line, separate workstream |
| 2000ep full paper run | 500ep covers paper "stable after 500ep" claim |

---

## Decision gates

After each phase, STOP and report. Do not auto-roll into next phase.

- **Gate after Phase 1**: Show diagnostic report. User decides if Phase 2 fix direction is right.
- **Gate after Phase 2**: Show smoke (5-10 ep) verifying fix. User decides if 500ep run is justified.
- **Gate after Phase 3**: Show 3-way comparison. User decides next step (paper write-up / B1 ladder probe / move to Simulink).

---

## Failure modes & exits

| If we hit | Action |
|---|---|
| Phase 1 shows no clear bottleneck | Re-survey; do not blindly add reward shaping |
| Phase 2 fix makes training worse | Revert; report; re-enter Phase 1 with new measurement |
| Phase 3 DDIC < no-control | Honest "negative result" report; do NOT cherry-pick seeds |
| Wall budget overrun (> 3 days total) | Halt; user decides scope cut |

---

## Artifacts (will be produced)

| Path | When |
|---|---|
| `results/andes_phase1_probe/` | Phase 1 |
| `quality_reports/audits/2026-05-03_andes_phase1_diagnostic.md` | Phase 1 |
| `scenarios/kundur/_phase1_signal_analyzer.py` | Phase 1 |
| `results/andes_phase2_*/` | Phase 2 |
| `results/andes_phase3_3seed/` | Phase 3 |
| `scenarios/kundur/_eval_nocontrol.py` | Phase 3 |
| `scenarios/kundur/_eval_fixed_adaptive.py` | Phase 3 |
| `quality_reports/replications/2026-05-03_andes_effective_agent_3way.md` | Phase 3 |

---

*Plan status: DRAFT. Awaiting approval before Phase 1 starts.*
