# Discrete Oracle Verdict — INCONCLUSIVE on physics, DECISIVE on engineering cost

- **Date:** 2026-05-01T21:1x
- **Goal:** Test if Discrete (Tustin) solver carries 248 MW Bus14 R-block LoadStep with max|Δf| ≥ 0.3 Hz, to decide whether to commit to full Discrete reconstruction (1-2 weeks).
- **Status:** Oracle test could NOT execute. New finding makes original plan obsolete.

---

## What was tried

1. ✅ Build `kundur_cvs_v3_disc_test.slx` via existing `build_kundur_cvs_v3_discrete_test.m`
   - powergui SimulationMode = Discrete, SampleTime = 50e-6, ode23t Variable-step
   - 44s build wall, 70 runtime vars saved
2. ✅ Loaded model + verified powergui Discrete params
3. ❌ **Compile/update FAIL — 1st block:** powergui internal `EquivalentModel1/Sources/Mux` complex/real signal mismatch on CCS sources (Real-Imag-to-Complex pattern)
4. ✅ Deleted all CCS blocks (4 sources + 4 GND + 4 RI2C + 8 Constants = 20 blocks)
5. ❌ **Compile/update FAIL — 2nd block:** different Mux port, same complex/real mismatch class
6. ✅ Investigation: 7 Real-Imag-to-Complex blocks remain, driving 7 Controlled Voltage Sources (ES1-4 + G1-3) — **all 7 internal EMF generators**

---

## Root cause

**Phasor-mode model uses complex-phasor signal architecture for ALL source-end blocks** (not just CCS).

- 4 ESS swing-eq closures: each computes `V_emf = |V|·exp(j·δ)` via `RI2C_ES{i}` → `CVS_ES{i}` (Controlled Voltage Source)
- 3 SG swing-eq closures: same pattern
- Plus 4 CCS blocks (deleted) using Real-Imag-to-Complex

In Phasor mode, powergui `EquivalentModel` expects complex-phasor inputs from these sources (consistent with Phasor solver's algebraic V·I* equations).

In Discrete mode, powergui `EquivalentModel` builds a **time-domain state-space** that expects **real-valued instantaneous voltage signals** (e.g. `V·sin(ωt + δ)` not `V·exp(jδ)`). The two architectures are **not signal-compatible**.

---

## Implication

**Cannot run a 4-6h cheap Discrete oracle** to test the physics question (does R-block produce ≥ 0.3 Hz at 248 MW under Discrete solver).

To test the physics, would need to first do **the same engineering work the full reconstruction requires**:

| Sub-task | Effort |
|---|---|
| Replace 7 RI2C → time-domain sinusoid generators | ~1-2 day |
| Replace 7 CVS → AC Voltage Source (Discrete-compatible) or custom sinusoid | ~1 day |
| Re-derive IC for time-domain (NR currently solves complex-phasor steady state) | ~1-2 day |
| Re-build all measurement blocks (Vabc, Iabc, Pe, omega) for time-domain | ~1-2 day |
| Verify model compiles + runs short sim | ~0.5 day |
| Then run oracle | 0.5 day |

**Total: ~5-7 days just to reach the "test if oracle PASS"** — i.e. half the full reconstruction budget.

---

## Decision-relevant finding

The original logic was:
- IF cheap oracle PASS → commit 1-2 weeks to full Discrete rebuild
- IF cheap oracle FAIL → cheap exit, accept +18%

That logic is now broken. Real choice:

| Path | Cost | Outcome |
|---|---|---|
| **A. Skip oracle, commit to Discrete blind** | 1-2 weeks | Maybe PASS (uncertain), 全套重建 |
| **B. Spend 5-7 days on partial-rebuild oracle, then decide** | 5-7 days + (1-2 weeks if PASS) | Better-informed but slow |
| **C. Don't go Discrete** | 0 | Accept +18%, pivot to P1 / P3 |

---

## Strengthens which side of the decision?

**Strengthens REJECT Discrete**, because:

1. **Cheap falsification path destroyed.** Original advantage of Discrete oracle (1-day GO/NO-GO) is gone.

2. **Engineering surprise revealed unknown depth.** The Phasor signal architecture pervades **all source-end blocks**, not just CCS. We didn't know this before today. There may be more such surprises waiting (NR re-derive in time-domain, measurement blocks, dispatch protocol adapter, paper_eval expectations on omega format).

3. **Project budget reality.** F4 v3 +18% is already a publishable anchor. Spending 1-2 weeks to chase paper +47% has high opportunity cost vs improving F4 baseline (which is the demonstrably-correct anchor).

4. **Paper +47% credibility unchanged.** No new evidence today that paper's number is achievable. Phasor weakness suggests Phasor is not what paper used, but doesn't prove paper used Discrete OR that paper's setup matches ours (Q-A H units, Q-D H_es,0 baseline still unresolved).

---

## Combined evidence summary (2026-05-01)

| Finding | Path implication |
|---|---|
| F2: R-block 248MW Phasor → 0.036 Hz | Phasor 弱 |
| H1: CCS@Bus7/9 1GW Phasor → 0.008 Hz | Phasor 弱 |
| F5: PHI=0 ablation → 0/4 agents contribute | PHI lock 是必要结构 |
| **TODAY: Discrete swap not block-compatible** | Discrete 不是 cheap option |

Cumulative pattern: project is at a **local optimum constrained by Phasor architecture choice early in the v3 build**. Escaping requires substantial reconstruction; staying accepts +18%.

---

## Recommendation

**Path C (don't go Discrete)**, AND:

1. **Lock in F4 v3 best (-11.999, +18%) as project's RL anchor**
2. **Pivot to P1 (action range expansion)** — same Phasor backend, requires small-signal stability analysis. Estimated +5-10pp. No reconstruction needed.
3. **Document the Phasor-Discrete architectural divergence** in `docs/decisions/` so future contributors don't re-discover this 5-7 day cost.
4. If paper -8.04 is binding requirement (not optional), reconsider Discrete as **separate project** with its own budget + scope, decoupled from current RL anchor.

---

## Artifacts (落盘)

```
scenarios/kundur/simulink_models/kundur_cvs_v3_disc_test.slx     ← built + closed (no save)
scenarios/kundur/simulink_models/kundur_cvs_v3_disc_test_runtime.mat
quality_reports/plans/p0_discrete_oracle_verdict.md              ← 本文件
```

`p0_e5_oracle.m` (Wave 1) 不能复用到 Discrete 因 model name 改后 source blocks 仍 Phasor-bound. 删除 disc_test.slx 还是保留为反面教材, 由用户决定.

---

*end — Discrete oracle verdict.*
