# Discrete Rebuild — Phase 0 (SMIB Oracle) → Phase 1 (Full v3)

**Status:** APPROVED 2026-05-03 (supersedes 2026-05-01 Path C REJECT verdict)
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Author:** user-authorized override; previous verdict at `quality_reports/plans/p0_discrete_oracle_verdict.md`

---

## 1. Why this plan supersedes 2026-05-01 REJECT

2026-05-01 verdict rejected Discrete on three grounds:
1. Cheap oracle compile-failed (RI2C → CVS pattern Phasor-bound)
2. Engineering surprise (signal architecture pervades all 7 sources)
3. F4 v3 +18% considered sufficient anchor

**User override (2026-05-03):** paper -8.04 / -15.20 / 47% is now hard requirement. F4 +18% no longer sufficient. Accept ~3 week investment.

**Mitigation of original rejection:** Phase 0 SMIB-first (2 days) keeps the cheap-oracle property by **isolating the simplest topology** (1 ESS + 1 R-load) where signal architecture migration cost is bounded.

---

## 2. Phase 0 — SMIB Discrete Oracle (2 days, HARD GO/NO-GO)

**Goal:** Falsify or confirm "Discrete + R-block step gives ≥ 0.3 Hz on minimal topology"

**Why SMIB first:** 2026-05-01 verdict found full v3 oracle requires 5-7 day partial rebuild before testing. SMIB has only 1 source = signal architecture rebuild cost ~4 hours, not days.

### Phase 0 acceptance gate

```
PASS criteria (ALL must hold):
  P0.1  Build compiles in Discrete mode (powergui SimulationMode='Discrete', SampleTime=50e-6)
  P0.2  Steady-state IC settles within 1s warmup (omega within 1.0 ± 0.001 pu)
  P0.3  248 MW R-block step produces max|Δf| ≥ 0.3 Hz at ESS terminal
  P0.4  Wall-clock for 5s sim < 10s (i.e. ≥ 0.5× real-time at 50μs step)
```

**EXIT routes:**
- All 4 PASS → **GO Phase 1** (full v3 rebuild)
- P0.3 FAIL → **HARD ABORT** — Discrete signal architecture works but physics doesn't deliver paper-scale response. Revert to PTDF path on `main`.
- P0.1 FAIL → 4-hour debug attempt; if still failing, ABORT.
- P0.4 FAIL but others PASS → continue with degraded speed budget (revisit after Phase 1)

### Phase 0 task list (2 days)

| Day | Task | Owner | Deliverable |
|---|---|---|---|
| 1 AM | Copy `probes/kundur/spike/build_minimal_cvs_phasor.m` from main worktree (uncommitted asset) | exec | `probes/kundur/spike/build_minimal_smib_discrete.m` skeleton |
| 1 AM | Swap powergui Phasor → Discrete; verify compile-only | exec | compile passes (or first-block error captured) |
| 1 PM | Replace RI2C → time-domain `Sin`/`Lookup Table` sinusoid generator | exec | source chain Discrete-compatible |
| 1 PM | Replace CVS → AC Voltage Source (Discrete-block library) | exec | new source block validated isolated |
| 2 AM | Wire R-load + Variable Resistor LoadStep + Vabc/Iabc/Pe measurements | exec | full minimal model compiles |
| 2 AM | Run 5s sim with 248 MW step at t=2s | exec | omega trace logged |
| 2 PM | Compare max\|Δf\| vs ≥ 0.3 Hz threshold; produce verdict.md | exec | `quality_reports/plans/2026-05-03_phase0_smib_discrete_verdict.md` |

---

## 3. Phase 1 — Full v3 Discrete Rebuild (10-15 days, contingent on Phase 0 PASS)

**Estimated effort:** 2-3 weeks. Final commit decision happens AFTER Phase 0 PASS.

### Phase 1 sub-tasks (high level only — detailed plan written after Phase 0 PASS)

| Sub-task | Days | Reuse |
|---|---|---|
| 1.1 Extend SMIB recipe to 7-source pattern (4 ESS + 3 SG) | 2-3 | Phase 0 source chain template |
| 1.2 Re-derive IC for time-domain | 2-3 | `compute_kundur_cvs_v3_powerflow.m` Y-bus stays; sinusoid IC requires phase + time-of-day mapping |
| 1.3 Rebuild measurement blocks (Vabc/Iabc/Pe phase-aware) | 2-3 | Phase 0 measurement template |
| 1.4 Adapt `disturbance_protocols.py` adapters | 1-2 | Pm channel adapters unchanged; LoadStep/CCS adapters tested fresh |
| 1.5 Adapt `slx_helpers/slx_step_and_read.m` for Discrete | 1 | base IPC stays; only set_param signatures may shift |
| 1.6 Re-run G1-G6 falsification gates on Discrete | 2 | `probes/kundur/probe_state/` package |
| 1.7 Run paper_eval no_control + trained baseline | 2 | `evaluation/paper_eval.py` should be backend-agnostic |

---

## 4. Asset reuse map

**Direct reuse, zero modification (paradigm-independent):**

| Asset | Path | Why reusable |
|---|---|---|
| Powerflow NR Y-bus | `scenarios/kundur/simulink_models/compute_kundur_cvs_v3_powerflow.m` | Steady-state algebra, paradigm-independent |
| IC numeric values | `scenarios/kundur/kundur_ic_cvs_v3.json` | NR result, just need phase-of-time interpretation |
| Disturbance dispatch adapters | `scenarios/kundur/disturbance_protocols.py` | frozen-dataclass; Pm channel paradigm-independent |
| Workspace var schema | `scenarios/kundur/workspace_vars.py` | naming, no Phasor binding |
| RL agents | `agents/sac.py`, `agents/ma_manager.py` | sim-backend independent |
| Paper eval | `evaluation/paper_eval.py` | reads omega/reward, paradigm-independent |
| Probe state orchestrator | `probes/kundur/probe_state/` | Phase architecture works on any backend |
| MATLAB session | `engine/matlab_session.py` | pure IPC |
| Run schema | `engine/run_schema.py` | data class |

**Adapt with patches (signal architecture changes):**

| Asset | Path | Change |
|---|---|---|
| v3 build script | `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | Replace RI2C+CVS → sinusoid+AC Voltage Source for 7 sources |
| step+read helper | `slx_helpers/slx_step_and_read.m` | Likely unchanged; verify Discrete set_param semantics |
| Bridge | `engine/simulink_bridge.py` | Should be transparent if .slx interface preserved |

**Build new:**

| Asset | Why |
|---|---|
| `build_minimal_smib_discrete.m` | Phase 0 oracle target |
| `build_kundur_cvs_v3_discrete.m` | Phase 1 main artifact (rename from `_test`) |
| Phase 0 verdict doc | `quality_reports/plans/2026-05-03_phase0_smib_discrete_verdict.md` |

**Recover from main worktree (uncommitted but useful):**

| Asset | Source path (main worktree) | Action |
|---|---|---|
| SMIB Phasor skeleton | `probes/kundur/spike/build_minimal_cvs_phasor.m` | Copy as starting point for `build_minimal_smib_discrete.m` |
| Prior Discrete test build | `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m` | Copy as Phase 1.1 reference (knows where compile failed) |
| 2026-05-01 verdict doc | `quality_reports/plans/p0_discrete_oracle_verdict.md` | Copy as historical reference; do NOT supersede here |
| Option G plans | `quality_reports/plans/option_g_*.md` | Copy as historical context |

---

## 5. Risk register + early-exit criteria

### Hard exit triggers (abort and revert to PTDF path)

| Trigger | Probability | Detection |
|---|---|---|
| **R1.** Phase 0 P0.3 FAIL (Δf < 0.3 Hz on SMIB) | Medium | Day 2 PM — physics doesn't deliver in simplest case → full rebuild won't either |
| **R2.** Phase 0 P0.4 FAIL by 5×+ (sim time > 50s for 5s sim) | Low | Day 2 — speed budget destroyed; Discrete impractical for RL |
| **R3.** Phase 1.2 IC re-derive divergent (NR doesn't converge or sin-frame inconsistent) | Medium | Day 3-5 of Phase 1 |

### Soft risks (continue but flagged)

| Risk | Mitigation |
|---|---|
| **S1.** Discrete signal works but model parameters don't match paper | Document in Phase 1 verdict; revisit H/D unit interpretation (Q-A, Q-D) before HPO |
| **S2.** F4 +18% anchor lost during rebuild | Keep `main` branch untouched; F4 anchor preserved on Phasor side |
| **S3.** Migration introduces regressions in `probe_state` G1-G6 | Run G1-G6 against Discrete v3 BEFORE training; freeze Phasor v3 G1-G6 verdict for comparison |

---

## 6. Worktree + branch hygiene

- **Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete` (clean path, no double-space)
- **Branch:** `discrete-rebuild` from `main@574b0f5`
- **Main worktree status:** `main` branch with PTDF work continuing in parallel
- **No cross-worktree dependencies expected** — Discrete branch self-contained after asset copy in §4
- **Merge strategy:** Phase 1 PASS → squash-merge to `main` as new physics baseline; Phase 0 FAIL → archive branch, no merge

---

## 7. Out of scope (explicit non-goals)

- Continuous EMT (ode23t variable-step) — too slow, not on table
- Time-domain detail beyond fundamental frequency 50Hz sinusoid — no harmonics, no PWM
- Replacing SimPowerSystems with alternative backend (OpenDSS, custom Python) — separate decision
- F4 hybrid Phasor improvements — frozen on `main`, not touched here

---

## 8. Definition of done

**Phase 0 done:** Verdict doc written with all 4 P0.x criteria evaluated. Either GO Phase 1 or HARD ABORT.

**Phase 1 done:** All of:
- v3 Discrete model compiles + steady-state IC settles
- 4 ESS dispatch G1-G6 gates all PASS (or documented exception)
- paper_eval no_control 5-episode mean cum_unnorm produced
- Trained run produces cum_unnorm comparable to paper -15.20 (within ±50% tolerance for first cut)

**Project done:** Phase 1 results documented + decision on whether to keep Discrete or revert to Phasor as main physics baseline.

---

## 9. Immediate next action

Execute Phase 0 Day 1 AM:
1. Copy `probes/kundur/spike/build_minimal_cvs_phasor.m` from main worktree to this worktree (skeleton)
2. Create `probes/kundur/spike/build_minimal_smib_discrete.m` based on skeleton
3. Swap powergui mode + first compile attempt

*end — Discrete rebuild plan, 2026-05-03.*
