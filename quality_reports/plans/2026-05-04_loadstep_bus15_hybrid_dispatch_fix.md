# Implementation Plan: LoadStep bus15 + Hybrid RNG Dispatch Fix (post-P2 latent bugs)

**Date:** 2026-05-04 (drafted 2026-05-03 EOD)
**Status:** DRAFT — pending operator approval
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Trigger:** P2 E2E v2 verdict 2026-05-03 (`quality_reports/specs/2026-05-03_phase4_speedup_p2.md` §11): GATE-PHYS partial — 12/15 dispatches bit-exact + 3 dispatches diverge.
**Parent ADR:** `docs/decisions/2026-05-03-probe-state-phase4-p2-parallelization.md`
**Bug debugger output:** debugger agent 2026-05-03 EOD (root-cause confirmed, see §1).

---

## §1 Overview

### 1.1 Bugs (FACT, from E2E v2 + debugger 2026-05-03)

| Dispatch | Serial | Parallel | Δ | Root cause |
|---|---|---|---|---|
| `loadstep_paper_bus15` | 0.0361 Hz | 0.1081 Hz | 0.072 | Bus15 breaker `InitialState='open'` + SwitchTimes compile-frozen → bus15 RLC permanently disconnected; amp writes electrically inert. Both modes' values are residual oscillation from preceding bus14 dispatch. |
| `loadstep_paper_random_bus` | 0.0361 Hz | 0.1081 Hz | 0.072 | Same as above — random_bus picks bus14 or bus15; bus15 picks reproduce the inoperative case. |
| `pm_step_hybrid_sg_es` | 0.1731 Hz | 0.1993 Hz | 0.026 | `HybridSgEssMultiPoint.apply` uses `rng.integers(1,4)` to pick `target_g`. Different RNG state across engine instances (serial dispatch [3] vs parallel dispatch [12]) → different `target_g` → different physics. |

### 1.2 What works (12/15 bit-exact PASS)

All `pm_step_proxy_*` (bus7 / bus9 / g1 / g2 / g3 / random_bus / random_gen) and `pm_step_single_es{1,2,3,4}` and `loadstep_paper_bus14` produce identical `max_abs_f_dev_hz_global` between serial and parallel modes (delta = 0.0 exactly). Confirms:
- P2 modules (α/β/γ/δ) themselves are correct.
- The 12 PM dispatches use `PM_STEP_AMP` workspace var (Constant block, runtime-tunable) — work correctly.
- `loadstep_paper_bus14` works because bus14 `InitialState='closed'` + IC 248 MW → amp write 248→0 is real disturbance.

### 1.3 Goal

Fix the 3 latent dispatch bugs so a re-run probe with `--workers=1` and `--workers=4` produces ALL_GATES_PASS including GATE-PHYS at 1e-9 strict.

### 1.4 Out of scope

- Touching P2 modules (α/β/γ/δ) — they're correct.
- Touching the 12 PM dispatches that PASS — they're correct.
- Changing the LoadStep adapter's amp-write semantics for bus14 (it works).
- Changing Hybrid's training-mode RNG behavior (only adding override knob).

---

## §2 Module Sequencing

### §2.1 Module L1 — bus15 InitialState='open' → 'closed' (build script)

**Goal:** Make bus15 LoadStep dispatch produce a real disturbance (electrically operative).

**Files modified:**
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m` (~line 451-454, where bus15 breaker is configured): change `'InitialState', 'open'` → `'InitialState', 'closed'`.
- Build-time default: `assignin('base', 'LoadStep_amp_bus15', 1)` (1W ≈ 0 MW) so closed breaker doesn't violate NR.
- `_reset_backend` in `env/simulink/kundur_simulink_env.py` (~line 902): change `LoadStep_amp_bus15 = 0.0` IC value to `1.0` (1W) — keeps breaker physically closed at IC without violating NR power balance.
- `compute_kundur_cvs_v3_powerflow.m`: 1W bus15 load is 1e-8 sys-pu, **negligibly below the 1e-3 NR tolerance** — no NR re-derive needed. Verify by reading the script.

**Acceptance:**
- `test_v3_discrete_ic_settle.m` (existing 1s 5/7 PASS baseline) still produces 5/7 PASS. (Bus15 1W load doesn't perturb baseline.)
- New unit test: 5s sim with bus15 amp write (e.g., 0→50 MW) produces non-trivial Δf >= 50 mHz (sanity: bus15 load change is now physically observable).

**Risk:**
- R_L1a: 1W → IC steady state shifts. Verify by reading NR output (1e-8 sys-pu is far below 1e-3 tolerance). Likely no observable effect.
- R_L1b: bus15 closed breaker changes startup transient. The 5/7 baseline includes ES4 oscillation already attributed to NR phasor mismatch — adding 1W is sub-noise.

**Estimated cost:** 30 min (5 min edit + 5 min sanity + 20 min IC settle re-verify).

### §2.2 Module L2 — Remove no-op LOAD_STEP_T writes (cleanup)

**Goal:** Remove misleading code that writes `LOAD_STEP_T` thinking it controls breaker timing — it's compile-frozen and silent no-op.

**Files modified:**
- `scenarios/kundur/disturbance_protocols.py::LoadStepRBranch.apply` (~line 507-510): remove `bridge.apply_workspace_var(LOAD_STEP_T, t_now+0.1)` calls.
- `env/simulink/kundur_simulink_env.py::_reset_backend` (~line 915-918): remove `LoadStep_t_bus14 = 100.0` and `LoadStep_t_bus15 = 100.0` writes.
- `scenarios/kundur/workspace_vars.py::LOAD_STEP_T`: keep schema entry but mark `effective_in_profile=frozenset()` for v3 Discrete + v3 Phasor; update `inactive_reason="Three-Phase Breaker SwitchTimes compile-frozen in Discrete+FastRestart per F2; runtime LOAD_STEP_T writes are silent no-ops. See plan 2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md."`.

**Acceptance:**
- All P2 + workspace_vars + adapter pytest still pass (we removed dead writes; nothing physical changes).

**Risk:**
- R_L2a: A test asserts the writes happen. Quick grep `LOAD_STEP_T.*apply_workspace_var` in tests to find. If found, update to assert no longer written.

**Estimated cost:** 15 min.

### §2.3 Module H1 — Hybrid deterministic target_g override

**Goal:** Make `pm_step_hybrid_sg_es` produce same physics across engine instances (serial vs parallel) by removing RNG state dependency in probe context.

**Files modified:**
- `scenarios/kundur/disturbance_protocols.py::HybridSgEssMultiPoint`: add field `target_g_override: Optional[int] = None` to the dataclass. In `apply`, replace `target_g = int(rng.integers(1, 4))` with:
  ```python
  if self.target_g_override is not None:
      target_g = int(self.target_g_override)
  else:
      target_g = int(rng.integers(1, 4))
  ```
- `probes/kundur/probe_state/_dynamics.py::run_per_dispatch`: when dispatching `pm_step_hybrid_sg_es`, configure the resolved adapter with `target_g_override=2` (G2 — middle SG, neutral default for probe). Training mode (no override) preserves existing RNG behavior.

**Acceptance:**
- Hybrid dispatch produces same `max_abs_f_dev_hz_global` across serial vs parallel (1e-9 abs).
- Existing training tests for hybrid (in `tests/test_disturbance_protocols.py`) still pass with `target_g_override=None` default (training-mode behavior unchanged).

**Risk:**
- R_H1a: hybrid was relying on RNG variation for training diversity. Probe-fixed value isn't a regression because probe is observation, not training.

**Estimated cost:** 15 min.

---

## §3 Test Plan

| Test | MATLAB? | Cost | Module |
|---|---|---|---|
| `tests/test_p2_loadstep_bus15_inoperative.py` (NEW): unit test on schema (LOAD_STEP_T effective_in_profile=frozenset()) | No | <1s | L2 |
| `tests/test_p2_hybrid_target_g_override.py` (NEW): unit test for HybridSgEssMultiPoint with target_g_override | No | <1s | H1 |
| `test_v3_discrete_ic_settle.m` re-run (existing) | Yes | ~30s | L1 |
| Probe Phase 4 re-run `--workers=1` | Yes | ~48 min | L1+L2+H1 E2E |
| Probe Phase 4 re-run `--workers=4` | Yes | ~16 min | L1+L2+H1 E2E |
| Gate eval (existing inline script) | No | <1 min | E2E verdict |

**Total wall:** ~65 min for full E2E re-validation; ~30 min for unit tests + sanity build.

---

## §4 Risk Register

| ID | Risk | Likelihood × Impact | Detection | Mitigation |
|---|---|---|---|---|
| R_L1a | NR power balance violated by 1W bus15 load | LOW × LOW | Read NR script; tolerance is 1e-3 sys-pu = 100 kW; 1W is 1e-5 of that | Trivial; no action needed |
| R_L1b | bus15 closed breaker shifts IC steady state | LOW × MED | `test_v3_discrete_ic_settle.m` 5/7 baseline | If shifted, accept new baseline (new fact) or set bus15 amp = 0.001 W (1 mW) |
| R_L2a | A test asserts LOAD_STEP_T writes happen | LOW × LOW | Grep tests for `LOAD_STEP_T.*apply_workspace_var` | If found, update test to assert removal |
| R_H1a | Hybrid training diversity broken | LOW × LOW (probe-only override) | Read hybrid training tests | Default `target_g_override=None` preserves training; only probe overrides |
| R_GLOBAL | This fix touches build script → .slx changes → triggers full rebuild | MED × MED | Smoke build + 1s IC test | Module β (P2) build-idempotency check catches stale .slx; rebuild is once-only |

---

## §5 Implementation Order

1. **NR sanity** (10 min): read `compute_kundur_cvs_v3_powerflow.m`, verify 1W bus15 load < tolerance; decide if NR re-derive needed. Likely answer: no.
2. **L1 build script change + IC re-validation** (30 min): edit `build_kundur_cvs_v3_discrete.m` line ~451-454 and ~assignin section; run `test_v3_discrete_ic_settle.m`; verify 5/7 baseline preserved.
3. **L2 cleanup** (15 min): remove no-op LOAD_STEP_T writes from adapter + env; update workspace_vars schema.
4. **H1 hybrid override** (15 min): adapter dataclass field + probe wiring.
5. **Unit tests for L2 + H1** (15 min): `tests/test_p2_*.py` additions.
6. **E2E re-run** (~65 min wall): serial + parallel + gate eval.
7. **ADR update** (15 min): `docs/decisions/...-p2-parallelization.md` GATE-PHYS verdict PARTIAL → PASS; reference this plan.
8. **Commit** (5 min): single commit `fix(loadstep,hybrid): bus15 InitialState=closed + LOAD_STEP_T cleanup + hybrid target_g_override`.

**Total:** ~3 hr nominal; ~4-5 hr with one NR-derive surprise.

---

## §6 Negative Scope (restated)

- DO NOT touch P2 modules α/β/γ/δ — they're correct.
- DO NOT change the 12 PM dispatches — they pass bit-exact.
- DO NOT change LoadStep adapter's amp-write for bus14 — works.
- DO NOT touch schema_version — additive only.
- DO NOT change G1-G6 verdict thresholds.
- DO NOT change `_verdict.compute_gates` logic.

---

## §7 ADR Stub

After implementation lands, draft `docs/decisions/YYYY-MM-DD-loadstep-bus15-initialstate-and-hybrid-deterministic.md` (post-implementation date).

Records 3 decisions:
1. bus15 InitialState='closed' + 1W IC load (over Variable Resistor alternative).
2. LOAD_STEP_T schema marked not-effective in any profile (no-op cleanup).
3. Hybrid target_g_override field with None default (probe-only fixed value).

---

## §8 Estimate

| Task | Cost |
|---|---|
| NR sanity | 10 min |
| L1 build edit + IC re-verify | 30 min |
| L2 cleanup (3 files) | 15 min |
| H1 adapter + probe wiring | 15 min |
| Unit tests | 15 min |
| E2E re-run (serial + parallel) | 65 min |
| ADR update | 15 min |
| Commit + push | 5 min |
| **Total nominal** | **~3 hr** |
| **Surprise budget** | **+1-2 hr** |

---

## §9 Trigger / Activation

This plan triggers when operator decides to fix latent bugs. **NOT blocking P2 commits** — P2 lands as-is with PARTIAL_PASS in ADR.

Activation checklist:
- [ ] P2 5 commits landed (P2 implementation, ADR, doc updates, etc.)
- [ ] LoadStep latent bug acknowledged in plan §1.0 registry of `2026-05-03_phase1_progress_and_next_steps.md`
- [ ] Operator GO on this plan

---

## §10 References

- P2 spec: `quality_reports/specs/2026-05-03_phase4_speedup_p2.md`
- P2 plan: `quality_reports/plans/2026-05-03_phase4_speedup_p2_plan.md`
- P2 ADR: `docs/decisions/2026-05-03-probe-state-phase4-p2-parallelization.md`
- Engineering philosophy: `quality_reports/plans/2026-05-03_engineering_philosophy.md` §6
- Phase 1.0 registry: `quality_reports/plans/2026-05-03_phase1_progress_and_next_steps.md`
- F2 compile-frozen finding: `2026-05-03_phase_b_findings_cvs_discrete_unlock.md`
- E2E v2 snapshots: `results/harness/kundur/probe_state/p2_e2e_serial/state_snapshot_20260503T214806.json`, `results/harness/kundur/probe_state/p2_e2e_parallel/state_snapshot_20260503T221230.json`
- Debugger output: aa5af7ecea447b62d (background agent 2026-05-03 EOD)

---

*end — LoadStep + Hybrid dispatch fix plan as of 2026-05-04 EOD draft.*
