# Phase 1 Progress + Next Steps — Single Source of Truth

**Status:** AUTHORITATIVE as of 2026-05-03 EOD session
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Supersedes:** `2026-05-03_phase1_next_steps.md` (early/stale, kept for history)

---

## §0 Quickstart for Fresh Session

> If you're a new AI agent picking up this work, read this section FIRST — it
> gives you the minimum context to verify state and choose next action.

### §0.1 Project background (1 paragraph)

Reproducing **Yang et al. TPWRS 2023** — multi-agent SAC reinforcement learning
controls 4 energy storage system (ESS) units' virtual inertia H and damping D
in a **Kundur 2-area power system**. The original Phasor-mode v3 model hit a
fundamental wall: **electrical disturbances (LoadStep, CCS injection) don't
propagate** in Phasor's static Y-matrix solver. The 2026-05-01 verdict
initially REJECTED Discrete migration on cost grounds, but on 2026-05-03 user
authorized override + Phase 0 SMIB Oracle (4.9 Hz @ 248 MW) falsified the
REJECT. The `discrete-rebuild` branch is the migration to Discrete EMT mode
with all module choices re-verified by pre-flights F11/F12/F13.

### §0.2 Worktree + branch (CRITICAL)

```
Path:  C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete
Branch: discrete-rebuild
```

⚠️  **NOT the same as the main worktree** — main is at
`C:\Users\27443\Desktop\Multi-Agent  VSGs` (double-space in path!) on `main`
branch. The main worktree's `kundur_cvs_v3.slx` and helpers may **shadow**
this branch's files in MATLAB path. If you see "shadowing" warnings, ensure
this worktree's `scenarios/kundur/simulink_models/` is FIRST in `addpath`.

### §0.3 Key new files (created on this branch, not in main)

| File | Purpose |
|---|---|
| `scenarios/kundur/simulink_models/build_dynamic_source_discrete.m` | Per-source helper (sin → 3 single-phase CVS in Y-config + Pe via V·I) |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m` | v3 Discrete build script (uses helper × 7) |
| `probes/kundur/spike/build_minimal_smib_discrete.m` | Phase 0 SMIB Oracle (validated 4.9 Hz) |
| `probes/kundur/spike/test_v3_discrete_ic_settle.m` | **Layer 2 TDD test — RUN THIS to verify state** |
| `probes/kundur/spike/test_{3phase_network,multisrc_coupling,ic_delta_mapping}_disc.m` | F11/F12/F13 pre-flight tests |
| `probes/kundur/spike/test_{cvs_disc_input,r_fastrestart_disc,var_resistor_disc,ccs_dynamic_disc,...}.m` | F1-F10 micro-experiments (parallel agent) |

### §0.4 Verify current state (1 command)

Via simulink-tools MCP (recommended):
```matlab
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/probes/kundur/spike');
addpath('C:/Users/27443/Desktop/Multi-Agent-VSGs-discrete/scenarios/kundur/simulink_models');
test_v3_discrete_ic_settle();
```

**Expected output (2026-05-03 EOD baseline, 1s sim, window [0.5,1]s):**
```
RESULT: G1: PASS  ω=0.99534 ± 0.00029
RESULT: G2: PASS  ω=0.99545 ± 0.00026
RESULT: G3: PASS  ω=0.99642 ± 0.00041
RESULT: ES1: PASS ω=0.99546 ± 0.00042
RESULT: ES2: PASS ω=0.99649 ± 0.00093
RESULT: ES3: FAIL ω=0.99663 ± 0.00177  (oscillate)
RESULT: ES4: FAIL ω=0.99669 ± 0.00102  (oscillate)
RESULT: 5/7 sources settled
```

**Branching logic:**
- 5/7 PASS as above → state matches doc; proceed with Phase 1.3a (ES3/ES4 oscillation diagnosis, see §4)
- **7/7 PASS** → someone solved 1.3a between sessions; update §3 + §4, move to Phase 1.4
- **< 5/7 PASS** → regression; `git log --oneline -10` to see what changed; diagnose before touching code
- **Build fails** → MATLAB engine state issue; `restart_engine` or `simulink_runtime_reset`

### §0.5 Read order (15 min total)

0. **§1.0 Tests Registry below** — 30-second scan; full landscape of completed tests + verdicts
1. **This doc §1-§5** — completed work + key findings + current state + next actions (5 min)
2. **`2026-05-03_engineering_philosophy.md`** — 13 principles + 8-item stop-trigger checklist (3 min) — reads BEFORE diagnosis
3. **`2026-05-03_phase_b_extended_module_selection.md`** — F1-F9 details if registry is insufficient (5 min, on demand)
4. **Main worktree `CLAUDE.md`** — project-wide coding conventions (skim, 2 min)

After this read-up, you have full context to either:
- Continue Phase 1.3a (ES3/ES4 oscillation diagnosis, see §4) — top of forward path
- OR pick a different sub-task from §5

### §0.6 Common pitfalls

1. **Wrong worktree** — running `git status` in `Multi-Agent  VSGs` (main) instead of `Multi-Agent-VSGs-discrete` will mislead you. Always verify `git rev-parse --abbrev-ref HEAD` returns `discrete-rebuild`.
2. **Shadow warnings** — MATLAB picks the wrong v3 build if main worktree is on path before this branch. Use absolute paths in `addpath` calls.
3. **`MaxDataPoints=2`** on To Workspace blocks — helper sets this for live RL training; in tests set to `'inf'` BEFORE `sim()` to capture full trace.
4. **CCS blocks disabled** — wrapped in `if false` in build script. Phase 1.5 sub-task. Don't enable yet.
5. **Continuous Integrator + FixedStepDiscrete = compile FAIL** (F9). Helper currently uses Continuous Integrator + FixedStepAuto (works). Don't change solver to FixedStepDiscrete without first migrating helper to Discrete-Time Integrator.
6. **DON'T MOVE THE GOALPOSTS** — if a test FAILS, do NOT relax acceptance criteria to make it pass. This is the #1 hallucination-disguised-as-progress trap.
   - Diagnose with the §4 hypothesis list (cheapest-first, falsifiable). Test each hypothesis with a concrete change (e.g. toggle a flag, modify one param) and observe whether the failure mode disappears.
   - Only AFTER root cause is confirmed by evidence, propose a fix. The fix may include relaxing acceptance criteria — but justified by physics (e.g. "swing mode damping time constant = 2s, so [4,5]s window is the correct physical acceptance"), not by "this makes the test pass".
   - Verdict claims like "Phase 1.X closed" REQUIRE evidence: actual sim output captured, FFT plot if frequency claimed, damping calc if mode-based, NR re-derive if IC-related. Anything stated in `RESULT:` lines that's not in the actual sim output IS HALLUCINATION.
   - If you find yourself thinking "the obvious answer is X, let me just write the verdict" — STOP. Run the falsification test for X first. If X is the right answer, the test confirms it cheaply. If X is wrong, you've avoided enshrining hallucination as truth.

   See `2026-05-03_engineering_philosophy.md` §6 for the full case study + 8-item stop-trigger checklist.

---

## §1 Completed Work

### §1.0 Tests Completed Registry (one row per test)

| ID | Script | Verdict | Key Result |
|---|---|---|---|
| **Phase 0** | `spike/build_minimal_smib_discrete.m` | ✅ PASS | 4.9 Hz @ 248 MW (16× threshold), 5.2× real-time |
| **F1** | `spike/test_cvs_disc_input.m` | ✅ PASS | sin / const real OK; complex phasor FAIL (= Phasor's blocker) |
| **F2** | `spike/test_r_fastrestart_disc.m` | ✅ PROVEN | Series RLC R is non-tunable in BOTH Phasor and Discrete |
| **F3** | `spike/test_var_resistor_disc.m` | ✅ PASS | Variable Resistor IS dynamic in Discrete + FastRestart |
| **F4** | `spike/test_ccs_dynamic_disc.m` | ✅ PASS | CCS responds to signal mid-sim (Phase 1.5 mechanism viable) |
| **F5** | `spike/test_pe_calc_options.m` | ✅ PASS | FIR Mean (20ms) settles 2.6× faster than 1st-order LPF |
| **F6** | `spike/test_solver_speed_disc.m` | ✅ PASS | DC trivial: solver/dt deltas < 5% |
| **F7** | `spike/test_phasor_vs_discrete_speed.m` | ⚠️ PARTIAL | Discrete 10× RT on AC trivial; Phasor side broken (config) |
| **F8** | `spike/test_ac_solver_sweep.m` | ✅ PASS | TBE/Tustin/BE × {25,50,100,200}μs all within 20% |
| **F9** | `spike/test_integrator_options.m` | ✅ PROVEN | Continuous Integrator FAILS in FixedStepDiscrete (use FixedStepAuto OR Discrete-Time Integrator) |
| **F10** | `spike/test_fastrestart_scale.m` | ⏸️ DEFERRED | Wiring blocked, retry post-1.4 |
| **F11** | `spike/test_3phase_network_disc.m` | ✅ PASS | Three-Phase Π Section Line + Load at v3-scale: I_err 0.8%, P_err 1.6% |
| **F12** | `spike/test_multisrc_coupling_disc.m` | ✅ PASS | 2 ESS perfect sync; **caught helper Zvsg bug** + fixed |
| **F13** | `spike/test_ic_delta_mapping_disc.m` | ✅ PASS | NR IC δ time-domain mapping electrically equivalent: Pe_err 0.6% |
| **Helper** | `spike/test_dynamic_source_helper.m` | ✅ VALIDATED | 4.93 Hz oracle (matches Phase 0's 4.90, <1% drift) |
| **v3 IC** | `spike/test_v3_discrete_ic_settle.m` | 🟡 5/7 PASS | G1/G2/G3/ES1/ES2 settle; ES3/ES4 oscillate (Phase 1.3a open) |
| **H1a** | inline (no script saved) | ❌ NR-confounded | both breakers open: ES4 std −42% / ES3 std −36%. Test BROKE NR consistency by removing 248 MW LS1 → cannot distinguish breaker IC from NR mismatch. Data: `phase1_3a_h1_open_breaker.mat` |
| **H1b** | `spike/test_h1_no_breaker_bus14.m` | ❌ FALSIFIED | NR-consistent variant (skip breaker, load 248 MW direct on Bus 14): ES3 std=0.001772 = baseline 0.001772 to 6 dp. Threshold 0.001. → breaker block is NOT the ES3 osc source. Closed Three-Phase Breaker (Ron=0.001 Ω) electrically equivalent to direct connect. Data: `phase1_3a_h1_nr_consistent.mat` |
| **Z (refactor)** | `scenarios/kundur/{model_profiles/kundur_cvs_v3_discrete.json, model_profile.py, workspace_vars.py, config_simulink.py, simulink_models/build_kundur_cvs_v3_discrete.m}` + `env/simulink/kundur_simulink_env.py` + `probes/kundur/probe_state/{probe_state.py, _dynamics.py, __main__.py}` + schema.json | ✅ ROUTE OPEN | Added `PROFILE_CVS_V3_DISCRETE` to workspace_vars; `PROFILES_CVS` / `PROFILES_CVS_V3` family constants replace literal model_name tuples in config_simulink + env (3 sites). New profile JSON loads same kundur_ic_cvs_v3.json. `t_warmup_s` constructor param + `--t-warmup-s` CLI flag (probe-context warmup override, default = T_WARMUP=10s). LOAD_STEP_AMP spec marked `effective_in_profile=frozenset({PROFILE_CVS_V3_DISCRETE})` (Phasor name-valid only; Discrete physically effective). `bus14_no_breaker` flag in build script (default false; H1b uses it). |
| **probe Z smoke** | `python -m probes.kundur.probe_state --phase 1,2,3 --sim-duration 3.0` (under `KUNDUR_MODEL_PROFILE=…kundur_cvs_v3_discrete.json`) | ✅ G2/G5 PASS | Phase 1: model_name=kundur_cvs_v3_discrete, n_ess=4, n_sg=3, n_wind=2, powergui_mode=Discrete, solver=FixedStepAuto, omega_tw_count_ess=4, omega_tw_count_sg=3 — all FACTs match build. Phase 3: 4 ESS distinct ω sha256, std-diff 1.189e-04 pu (G5 PASS). All 4 ESS settle ω=1.0±1e-5 in [4-5]s window after 10s warmup. Snapshot: `results/harness/kundur/probe_state/state_snapshot_20260503T175758.json` (impl 0.5.0, schema 1) |
| **FR microtest** | `probes/kundur/spike/test_fastrestart_v3_discrete.py` | ✅ FR_VIABLE | FastRestart on v3 Discrete: physics rel err 2.46e-08 (off vs on-repeat) << 1e-5 threshold. Wall: off-1=6.75s, off-2=1.78s (warm), on-repeat=1.16s. Per-sim speedup 1.5× over warm baseline (35% reduction). param-tune sanity (M_1=23.5) rel err 8.9e-06 — solver propagates changes correctly. Recommend opt-in via BridgeConfig.fast_restart flag, default off. |
| **alpha probe** | `python -m probes.kundur.probe_state --phase 1,2,3,4 --sim-duration 3.0 --t-warmup-s 5.0` (no FR, v3 Discrete) | 🟡 G1/G2/G3/G5 PASS, **G4 REJECT** | Phase 1+2+3+4 wall=37.9 min (Phase 4 = 36.1 min, 12 dispatch OK + 3 LoadStep ERROR for missing LOAD_STEP_TRIP_AMP profile). G4 REJECT: 1 distinct responder signature across 12 dispatches (1mHz threshold too low for v3 Discrete EMT coupling — every agent always above 74 mHz). Snapshot: `state_snapshot_20260503T184730.json`. |
| **D3 RNG fix** | `_dynamics.py:273` (1-line, applied 2026-05-03) | ✅ APPLIED | env.reset(seed=hashlib.md5(d_type)) per dispatch; deterministic per-dispatch RNG so `pm_step_proxy_random_*` no longer collapse to same RNG state across loop. Verified: `pm_step_proxy_random_gen` now distinct from `pm_step_proxy_g3` post-fix. |
| **2 pytest fixes** | `tests/test_kundur_workspace_vars.py::test_spec_for_per_sg_v3_family` + `tests/test_disturbance_protocols.py::test_known_types_includes_all_14_plus_single_vsg` | ✅ APPLIED | Z route widened PMG_STEP_AMP profiles to PROFILES_CVS_V3 + disturbance registry grew 14→22 — tests updated, 83 passed. |
| **dispatch collision diag** | inline (no script) — debugger 2026-05-03 | 🔵 D1+D3 split | 3 collision groups in alpha snapshot. **D1 (naming overlap)**: `pm_step_proxy_bus7 ≡ pm_step_single_es1` and `pm_step_proxy_bus9 ≡ pm_step_single_es4` are synonyms by adapter design (target_indices=(0,) and (3,) respectively) — not a bug, doc clarification only. **D3 (RNG state)**: `pm_step_proxy_random_*` collapsed because `env.np_random` not re-seeded in probe loop — fixed via D3 RNG fix above. |
| **FR integration** | `engine/simulink_bridge.py` + `env/simulink/kundur_simulink_env.py` + 3 probe files | ❌ REVERTED 2026-05-03 EOD | bvc00fouh (`--fast-restart` Phase 4 sweep) measured 46 min wall, **+28% vs alpha 36 min**. Microtest's 35% per-sim speedup did not translate to integrated env.reset+warmup loop (per-dispatch wall ~176s vs alpha 181s, similar; FR added overhead without gain). Reverted: `simulink_bridge.py:301` `_apply_fast_restart()` call commented out (1 line). Method body + BridgeConfig.fast_restart field + CLI flag retained as dead code for future Option C refactor. Physics zero change (G1-G5 verdicts identical to alpha). |
| **G4 floor follow-up** | (deferred) `dispatch_metadata.py` — D1 agent recommendation | 🔵 PENDING | Add `g4_position_hz` field to `ProbeThresholds` (~0.10 Hz for v3 Discrete). Current `g1_respond_hz=1e-3` too low: every agent responds > 74 mHz under any dispatch in EMT-coupled v3 Discrete, collapsing all 12 signatures to `(0,1,2,3)`. Not blocking; threshold tune for next paper anchor. |
| **Hybrid floor follow-up** | (deferred) `dispatch_metadata.py::pm_step_hybrid_sg_es.expected_min_df_hz` — D2 agent recommendation | 🔵 PENDING | Floor 0.30 Hz derived from F4_V3_RETRAIN_FINAL_VERDICT mean (DIST_MAX=3.0 sweep, mean magnitude 1.55). Probe runs at fixed mag=0.5 (32% of historical mean) — observed 0.177 Hz consistent with mag-linear scaling (0.65 × 0.32 ≈ 0.21). Recalibrate floor to ~0.15-0.20 Hz for fixed mag=0.5, OR run probe at higher mag. Not blocking; measurement-protocol mismatch not model degradation. |
| **LoadStep adapter fix** | `disturbance_protocols.py::LoadStepRBranch.apply` + `kundur_simulink_env.py::_reset_backend` + `workspace_vars.py::LOAD_STEP_T schema` | ✅ APPLIED 2026-05-03 EOD | bvc00fouh snapshot showed 3 LoadStep dispatches bitwise-identical 0.1081 Hz = Phase 3 IC settle drift — breaker fired during warmup at compile-baked `LoadStep_t=5.0`, never inside measurement window. Fix: adapter writes `LOAD_STEP_T = t_now + 0.1` post-amp; env reset pushes `LOAD_STEP_T` to 100s (warmup safe). Schema added LOAD_STEP_T (PROFILES_CVS_V3, effective only in Discrete). 117 pytest pass, 0 regression. |
| **P2 Module α** | `probes/kundur/probe_state/{__main__.py, _subset.py, _dynamics.py::_apply_dispatch_subset, probe_state.py}` + `tests/test_p2_dispatch_subset.py` + `tests/test_p2_subset_cli_validation.py` | ✅ APPLIED 2026-05-03 | argparse adds `--workers` (int, default 1) + `--dispatch-subset` (str/tuple/None). `_parse_subset_spec` resolves "0,3,7" indices or "name1,name2" names against effective dispatch list. Module α validates `workers > 1` incompatible with `--phase 5/6` (raises SystemExit). Mode banner per S7 logged at run() start. Default workers=1 preserves serial path bit-identical (M1). 88+12 unit tests pass. |
| **P2 Module β** | `probes/kundur/probe_state/_build_check.py` + `probe_state.py::_ensure_build_current` + `tests/test_p2_build_check.py` | ✅ APPLIED 2026-05-03 | `is_build_current(slx_path, deps)` mtime-compares .slx vs build script + helper + IC JSON. Gated behind `self.workers > 1`; serial mode bypass. If stale, `MatlabSession.get('default').eval('build_kundur_cvs_v3_discrete()')` rebuilds once before workers fork (R_P2 mitigation). Re-raises on rebuild failure. 6 unit tests pass. |
| **P2 Module γ** | `probes/kundur/probe_state/_orchestrator.py` (185 LOC: slice_targets / spawn_worker / wait_for_all) + `probe_state.py::_run_parallel` (~80 LOC) + `tests/test_p2_orchestrator.py` + `tests/test_p2_serial_compat.py` | ✅ APPLIED 2026-05-03 | Round-robin `targets[k::n_workers]` slicing. Subprocess.Popen × N workers; worker 0 runs `--phase 2,3,4`; workers 1..N-1 run `--phase 4`. Each worker has private MATLAB engine + private output dir `p2_worker_<n>/`. SIGTERM @ 4hr timeout, SIGKILL @ +30s. Empty slices skipped. Decision 4.3 trust-worker-0 for phases 2/3. 24+10 unit tests pass. |
| **P2 Module δ** | `probes/kundur/probe_state/_merge.py` (127 LOC: merge_snapshots / load_worker_snapshot / MergeError) + `probe_state.py::_run_parallel` merge call site + `tests/test_p2_merge.py` | ✅ APPLIED 2026-05-03 | Phase 1 from parent; phase 2/3 from worker 0; phase 4 dispatches combined disjoint (raises MergeError on overlap, R_P3 mitigation). New `phase4_per_dispatch.parallel_metadata` key (Y3 telemetry: n_workers, worker_subsets, worker_meta, dropped_dispatches). Non-zero exit codes surfaced into errors[] (S6). Worker errors[] forwarded with dedup. Decision 4.4: verdict centrally recomputed via `_verdict.compute_gates(merged)`. 17 unit tests pass + diff_handles_merged regression (R_P8/M5). |
| **Y4 license smoke** | `probes/kundur/spike/test_y4_license_smoke.py` | ✅ GATE_LIC_PASS @ N=4 (2026-05-03) | 4 subprocess.Popen workers each starting matlab.engine concurrently. Cold start times: 11.15s / 10.55s / 10.78s / 8.27s. Total wall 11.3s (true parallel). 4/4 exit_code=0. RAM peak ~5 GB (= 4 × 1.3 GB; under spec M8 8 GB threshold). M7 BLOCKED → PASS. Unblocks P2 E2E. |
| **P2 spec + plan** | `quality_reports/specs/2026-05-03_phase4_speedup_p2.md` + `quality_reports/plans/2026-05-03_phase4_speedup_p2_plan.md` | 🔵 APPROVED PENDING IMPL | Subprocess parallelization spec (11 sections, 5 acceptance gates GATE-PHYS/WALL/G15/LIC/RAM, 3 BLOCKED items) + impl plan (4 modules α/β/γ/δ, 11 hr estimate). Triggered by alpha 2168s ≥ 1500s threshold. Gated on M7 4-engine license smoke (Y4 helper) before E2E. FR baseline DEFERRED — alpha used as immutable trigger reference. |
| **P2 E2E v1** | `python -m probes.kundur.probe_state --phase 1,2,3,4 --workers 4` (2026-05-03) | ❌ FAILED root-cause | All 4 workers exit_code=1 in 139s, 0 dispatches done. Root cause: workers launched with `--phase 4` (worker 0 with `2,3,4`) — Phase 1 missing → `valid_targets=[]` in `_dynamics.run_per_dispatch` → `_parse_subset_spec` rejected all subset names as unknown → SystemExit. Plan §2.3 design assumed workers don't need Phase 1; FALSIFIED. |
| **P2 spawn_worker fix** | `_orchestrator.py:113-122` (1-line: `phases_arg = "2,3,4"/"4"` → `"1,2,3,4"/"1,4"`) + `tests/test_p2_orchestrator.py` (2 assertion updates) | ✅ APPLIED 2026-05-03 EOD | Add Phase 1 to all workers. Plan §2.3 + spec §11 amended with drift note. 24 unit tests pass. Cost: +~15s wall (parallel Phase 1 across workers). |
| **P2 E2E v2** | re-run parallel-only (`--workers 4`, serial baseline preserved at p2_e2e_serial/state_snapshot_20260503T214806.json) | 🟡 PARTIAL PASS | Serial: 47.9 min wall, 15 dispatches OK, G1/G2/G3/G5 PASS, G4 REJECT. Parallel: **984.7s = 16.4 min wall, 4/4 workers exit_code=0, 2.92× speedup, 0 dropped**. **GATE-WALL/G15/LIC PASS**. **GATE-PHYS PARTIAL: 12/15 bit-exact (delta=0.0)**, 3 dispatches diverge: `loadstep_paper_bus15` (Δ=0.072 Hz), `loadstep_paper_random_bus` (Δ=0.072), `pm_step_hybrid_sg_es` (Δ=0.026). |
| **LoadStep latent bug diagnosis** | debugger agent 2026-05-03 EOD (background) | 🔵 ROOT CAUSE LOCKED | 3 GATE-PHYS fails are NOT P2-introduced. Root cause: (1) Three-Phase Breaker `SwitchTimes` compile-frozen (F2 mechanism applies) → LOAD_STEP_T runtime writes are silent no-ops; (2) bus15 `InitialState='open'` + frozen breaker → bus15 RLC permanently disconnected → amp writes electrically inert; (3) hybrid `target_g` from RNG state varies across engine instances. Both serial 0.036 and parallel 0.108 for bus15 are "wrong" (residual from preceding bus14 dispatch). Tracked in `quality_reports/plans/2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md` (~3 hr fix, separate session). |

Detailed evidence: F1-F3 → `2026-05-03_phase_b_findings_cvs_discrete_unlock.md`; F4-F9 → `2026-05-03_phase_b_extended_module_selection.md`; Phase 0 → `2026-05-03_phase0_smib_discrete_verdict.md`; F11-F13 + helper + v3 IC → commits `b6e5d97` / `84b6036` / `68a669f` / `7062695`.

### §1.1 Phase 1.1 — Source-chain Helper + LoadStep + v3 Compiles

- New helper `build_dynamic_source_discrete.m` encapsulates SMIB pattern (theta + 3 sin + 3 single-phase CVS + Y-config + Zvsg + VImeas + Pe via V·I) — replaces ~270 lines of v3 inline pattern with one function call × 7 sources
- LoadStep migrated: Series RLC R (compile-frozen) → Three-Phase Breaker + Three-Phase Series RLC Load
- CCS blocks wrapped in `if false` (Phase 1.5 to restore with sin-driven pattern)

### §1.2 Phase 1.1+ — Full Network 3-phase Migration

- 19× single-phase Pi Section Line → Three-Phase PI Section Line (with propagation-speed clamp for short lines)
- 2× loads + 2× shunts + 2× Wind PVS migrated to 3-phase variants
- Bus net wiring: per-phase anchor maps (A/B/C), 3-port-per-block registration

**Result**: 5/7 sources settle (see registry §1.0 v3 IC row); ES3/ES4 oscillation is Phase 1.3a (§4).

---

## §2 Key Findings (Surprises + Constraints)

| # | Finding | Source | Impact |
|---|---|---|---|
| K1 | v3 CVS block accepts sin signal in Discrete; rejects complex phasor | F1 (test_cvs_disc_input.m) | Source chain rewrite scope = sin generators only, not CVS replacement |
| K2 | Series RLC R-block compile-frozen in BOTH Phasor and Discrete + FastRestart | F2 (test_r_fastrestart_disc.m) | Must use Breaker+Load for LoadStep, not R-block |
| K3 | Variable Resistor IS dynamic in Discrete + FastRestart (alternative LoadStep) | F3 (test_var_resistor_disc.m, parallel agent) | 2nd LoadStep mechanism available if needed |
| K4 | Continuous Integrator FAILS in FixedStepDiscrete solver | F9 (test_integrator_options.m, parallel agent) | Currently using FixedStepAuto so OK; switch to Discrete-Time Integrator if going pure Discrete |
| K5 | Three-Phase Source MUST have NonIdealSource='on' when connected to Π line | F11 + Phase 1.1+ surprise | "Ideal V parallel C" compile error otherwise |
| K6 | Helper needed per-phase Zvsg (R+L) between CVS and VImeas (was missing) | F12 surprise | Without it, ideal CVS in parallel with downstream Π-line shunt-C breaks compile |
| K7 | v3 short-line params (L_short × C_short) give v_propagation > c | Phase 1.1+ surprise | Auto-clamp C in build script to keep speed ≤ 280,000 km/s |
| K8 | NR IC `(V_emf_pu, δ_rad)` directly transferable to time-domain via Vpk·sin(ωt+δ) | F13 | No NR re-derive needed — saves 2-3 days estimated work |

---

## §3 Current State

**v3 Discrete model** (`scenarios/kundur/simulink_models/kundur_cvs_v3_discrete.slx`):
- Compiles 0 errors / 0 warnings
- 70 runtime workspace vars (matches Phasor v3)
- 5/7 sources settle to ω = 0.995 ± 0.0009 within 1s
- 2/7 (ES3, ES4) oscillate at std 0.001-0.002 around ω = 0.997
- Sim wall (1s): 1.74s
- Sim wall (5s, measured 2026-05-03): 4.99s (1.0× real-time, init overhead amortized)
- Sim wall (10s, measured 2026-05-03): 8.95s (1.1× real-time)

**Z refactor route opened (2026-05-03 EOD)**:
- Model profiles abstraction added: `model_profiles/kundur_cvs_v3_discrete.json` + schema
- workspace_vars.py: `PROFILE_CVS_V3_DISCRETE` + `PROFILES_CVS` / `PROFILES_CVS_V3` constants
- env config 3 sites: config_simulink.py / bridge / kundur_simulink_env.py using profile constants (not literal model names)
- probe_state: Phase 1+2+3 smoke runs G2/G5 PASS; all 4 ESS settle ω=1.0±1e-5 after 10s warmup
- FastRestart viable on v3 Discrete: 1.5× reset speedup, physics err 2.46e-08 (not yet integrated, opt-in flag ready)

**What works structurally**:
- Source chain (helper-based) ✓
- 3-phase network (lines + loads + shunts + wind) ✓
- LoadStep mechanism (Breaker+Load) ✓
- Bus net wiring (per-phase anchor maps) ✓
- IC numerics (V_emf_pu × sin pattern) ✓ (mostly)
- Model profile abstraction + route ✓

**What's incomplete**:
- ES3/ES4 oscillation root cause (Phase 1.3a — H1 FALSIFIED, H2 is now leading, see §4)
- CCS injection (disabled, Phase 1.5; LOAD_STEP_TRIP_AMP / CCS_LOAD_AMP profiles still Phasor-only)
- Continuous Integrator → Discrete-Time Integrator (FixedStepAuto bypass; Phase 1.5+ optimization)
- Pe FIR filter (currently instantaneous V·I, oscillates at 100 Hz; Phase 1.5+ optimization)

---

## §4 Known Issues — Phase 1.3 To Diagnose

### Issue 1.3a — ES3/ES4 oscillation (UNRESOLVED, root cause not proven)

**Symptoms** (1s sim, window [0.5,1]):
- ES3 (Bus 14) std=0.00177, ES4 (Bus 15) std=0.00102 — failed std<0.001 threshold
- ES1 (Bus 12) and ES2 (Bus 16) settle fine — same ESS topology, different bus
- Bus 14/15 differ from Bus 12/16 in having a Three-Phase Breaker + Three-Phase Series RLC Load
  attached. Bus 14 LS1 InitialState='closed' (paper Task 2 pre-engaged 248 MW); Bus 15 LS2 InitialState='open'.

**Spectrum diagnostic finding** (1s sim, raw FFT @ window [0.5,1], data in `phase1_3a_spectrum_diag.mat`):
- All 7 sources show same dominant 2 Hz / 4 Hz / 6 Hz harmonic structure
- BUT: shared frequency does NOT prove same root cause — Bus 14/15 attachments could excite the
  same natural mode preferentially. Magnitude ordering is not yet code-verified beyond raw FFT power.

**Hypotheses to test** (cheapest first, in original §4 order):
1. **H1**: LS1 closed-state × Π-line shunt-C transient.
   - **H1a (2026-05-03)**: open both breakers, re-run 1s test → ES3 std −36%, ES4 → PASS, but
     this BROKE NR consistency (removed 248 MW LS1 from a topology NR solved with it).
     Result confounded — could be breaker IC OR NR mismatch.
   - **H1b (2026-05-03, NR-consistent)**: skip breaker, connect 248 MW load DIRECTLY to Bus 14
     (NR consistency preserved). Result: ES3 std = 0.001772 = baseline 0.001772 (6 dp).
     **VERDICT = H1 FALSIFIED.** Closed Three-Phase Breaker (Ron=0.001 Ω) is electrically
     equivalent to direct connection at the precision of std-over-50000-samples. Breaker block
     is NOT the ES3 osc source.
   - Inference for H1a: the 36% std drop in H1a came from the NR mismatch (= H2 territory),
     not from removing the breaker IC transient.
2. **H2**: Bus 14/15 power-flow imbalance from LS1 pre-engaged → re-derive NR with LS1 active and use updated Pm.
   - **Now the leading hypothesis** given H1 falsification. Need to read
     `compute_kundur_cvs_v3_powerflow.m` (or equivalent) to scope cost.
3. **H3**: Solver step too coarse for Breaker-Load-Π interaction → try 25 μs step.
4. **H4**: Three-Phase PI Section Line zero-seq params wrong → try [Lk, 1.5×Lk] instead of [Lk, 3×Lk].

**Status**: H1 FALSIFIED (2026-05-03, test H1b). Evidence: three-phase breaker + load at Bus 14 electrically equivalent to direct 248 MW load at breaker precision. Next: scope H2 NR re-derive cost (read `compute_kundur_powerflow.m`), design NR-consistent falsification test, run, decide.

**Build script change**: `build_kundur_cvs_v3_discrete.m` gained `bus14_no_breaker` flag
(default false, preserves baseline). Override via `assignin('base','bus14_no_breaker',true)`.
Used by `test_h1_no_breaker_bus14.m`.

### Issue 1.3b — Steady-state ω = 0.995 (UNRESOLVED, root cause not proven)

**Symptoms**: All 7 sources sit at 0.995-0.997 instead of exactly 1.0 (after 1s).

10s observation (read-only data in `phase1_3a_10s_settle.mat`, not a fix): mean ω trajectory
0.995 (@1s) → 0.9998 (@5s) → 1.0000 (@10s). Could be either (a) physical damping of 2 Hz swing mode,
or (b) latent NR/EMT phasor mismatch slowly draining via shunt losses. Diagnosis pending H1 outcome
— if H1 PASSES (open breaker → ES3/ES4 settle in 1s), then 1.3b is also a breaker-driven transient
artifact. If H1 fails, 1.3a/1.3b need separate root-causing.

---

## §5 Forward Path

| Phase | Goal | Estimated effort |
|---|---|---|
| **1.3a** | H2 test (NR re-derive) → diagnose ES3/ES4 oscillation root | 1-2 hours |
| **1.3b** | Diagnose ω = 0.995 vs 1.0 (or accept as tolerance) | 1-3 hours |
| **1.4** | 248 MW LoadStep oracle on full v3 Discrete (paper anchor) | 2-4 hours |
| **1.5** | Restore CCS injection (sin-driven 3-phase, Phase 1.5 sub-design) | 4-6 hours |
| **1.5+** | Speed optimization (TRIGGERED ONLY — see §6) | 0 hours default; 30 min if triggered |
| **1.6** | Update env config + paper_eval to use v3 Discrete (mostly done by Z route) | 1-2 hours |
| **1.7** | First trained policy run on v3 Discrete | 1-2 days |

**Optimistic remaining**: 4-6 days (vs original 8-12 day Phase 1 estimate)
**Realistic remaining**: 1-2 weeks (with surprise budget)

---

## §6 Training Time Risk Mitigation — Lean / Trigger-on-Demand

**Methodology shift (2026-05-03 EOD review)**: Original F14-F17 list was "test for testing's sake" — pre-optimization with no decision context. Replaced with measure-first / optimize-only-if-needed.

### §6.1 Baseline projection from existing data

From Phase 1.1+ IC test (1s sim → 1.74s wall, 1.7× real-time at v3 scale):

```
Single 5s episode sim   ≈ 1.7 × 5s = 8.5s wall
Single episode reset    ≈ 1s wall (FastRestart, assumed)
Per-episode total       ≈ 9.5s wall
200 episodes pure sim   ≈ 32 min wall
+ RL overhead (SAC, replay buffer, etc.) ≈ +30-50%
TOTAL TRAINING WALL     ≈ 40-60 min  (acceptable)
```

This projection comes from data we already have (v3 IC test). **No additional speed tests needed if projection holds.**

Read-only longer-sim measurements (2026-05-03, NOT yet a verified baseline — depends on Phase 1.3a outcome):
- 5s sim wall = 4.99s (1.0× real-time)
- 10s sim wall = 8.95s (1.1× real-time)

These look better than the 1.7× projection (init overhead amortizes), but only become the planning
baseline once Phase 1.3a closes with a proven root cause.

### §6.2 Trigger condition for speed tests

Defer all speed optimization to AFTER trial training:

```
Phase 1.6 接 paper_eval / probe_state
   ↓
Run TRIAL training: 10-20 episodes on v3 Discrete
   ↓
Measure actual wall-clock per episode + reset
   ↓
Extrapolate to 200 episodes
   ├─ < 2 hr  → ship as-is, no speed tests needed
   ├─ 2-4 hr  → run minimal speed test (D5 only, ~10 min) — FastRestart toggle
   └─ > 4 hr  → run full triggered speed test bundle (~30 min)
```

### §6.3 Triggered Speed Test Bundle (run only if 200-episode projection > 2 hr)

If the trigger fires, run a SINGLE combined test that resolves the 3 highest-ROI module decisions in ~30 min:

| Decision | Variables | Acceptance |
|---|---|---|
| **D2** Sample time | dt ∈ {50, 100, 200} μs | largest dt with Pe error < 1% and IC settle stable |
| **D3** Integrator+Solver pair | (Continuous + FixedStepAuto) vs (Discrete-Time + FixedStepDiscrete) | faster pair if speedup ≥ 1.5× |
| **D5** FastRestart | on vs off (only matters at v3-scale; trivial result expected to be similar to F3/F4) | adopt if reset speedup ≥ 3× |

Combined sweep: 3 dt × 2 integrator-solver × 2 FastRestart = 12 configs × ~5s wall each = 60s + setup. Total wall < 30 min including writing the test.

**Skipped from earlier roadmap** (low ROI relative to cost):
- D1 Solver type sweep — F8 trivial result said all similar; v3 retest probably wastes time
- D4 Pe filter — quality issue not speed (deferred to RL signal-quality review, not speed)
- D6 3-phase line variant — invasive change for unclear gain
- D7 Source NonIdeal SCL — minor effect
- D8 Training parallelism (multi-env) — infrastructure decision, separate scope

### §6.4 Why this is the right framing

YAGNI: don't optimize what's not measured to be slow. Existing data already projects 40-60 min training, comfortably under any reasonable threshold. If projection holds → 0 wasted hours. If it fails → 30 min of targeted tests (not 4-8 hr).

Pre-optimization risk mitigation is not free — it costs hours of design + execution that could go to actual training, RL agent tuning, or paper-anchor validation. By deferring optimization to "triggered on miss", we preserve that budget for higher-leverage work.

---

## §7 Phase 1 Effort vs Original Estimate

| Sub-task | Original estimate | Actual (so far) | Notes |
|---|---|---|---|
| 1.1 Source-chain rewrite | 2-3 days | ~2 hours | Helper pattern + scaling factor 7 |
| 1.2 IC re-derivation | 2-3 days | **0 (F13 confirmed direct reuse)** | Major saving |
| 1.3 Measurement blocks | 2-3 days | ~1 hour | V-I Measurement directly compatible |
| 1.4 Integration + first oracle | 1-2 days | TBD (Phase 1.4 not done) | |
| 1.5 CCS restoration | (not in original) | TBD (~half day) | |
| Network 3-phase | (not in original — surprise) | ~3 hours | F11+F12+F13 pre-flights crucial |
| Pre-flight micro-experiments | (not in original) | ~2 hours | F11/F12/F13 + helper validation |

**Pattern**: when pre-flights are done, integration goes 5-10× faster than estimated. The "surprise budget" gets eaten by pre-flight discoveries (which is what they're for).

---

## §8 Architecture Decision Log (additions since 2026-05-03)

1. **Helper-based source-chain instead of inline rewrite**:
   - Pros: 1 build_dynamic_source_discrete.m owns all swing-eq + sin + CVS + V-I + Pe per source. Easier to fix bugs, test in isolation, reuse.
   - Cons: helper signature changes propagate to multiple sites. Mitigated by struct-input pattern.

2. **LoadStep: Breaker+Load (not Variable Resistor)**:
   - F3 confirmed Variable Resistor works in Discrete, but it's single-phase × 3.
   - Breaker+Load is 2 blocks, directly 3-phase, cleaner.
   - Choice locked at 2026-05-03.

3. **Solver = FixedStepAuto (not FixedStepDiscrete)**:
   - F9 says Continuous Integrator FAILS in FixedStepDiscrete.
   - Helper currently uses Continuous Integrator.
   - FixedStepAuto auto-selects ode4 (handles continuous), works for our IC test.
   - Phase 1.5+ optimization: switch to FixedStepDiscrete + Discrete-Time Integrator if speed gain warrants.

4. **CCS injection: deferred to Phase 1.5**:
   - F4 confirmed CCS works in Discrete with sin signal.
   - Not blocking Phase 1.4 oracle (LoadStep Breaker+Load is sufficient).
   - Will be restored when needed for paper-protocol comparison or freq-rise scenarios.

---

## §9 Phase 1.3a Diagnostic Artifacts (read-only data, 2026-05-03)

These are MEASUREMENTS, not verdicts. Used as inputs to the §4 H1-H4 hypothesis tests, which are
still pending (see §0.6 pitfall #6 — measurements ≠ root cause).

Saved to `scenarios/kundur/simulink_models/`:
- `phase1_3a_spectrum_diag.mat` — 1s sim ω time series for all 7 sources
- `phase1_3a_10s_settle.mat` — 10s sim ω time series

Per-window mean / max-std observations (10s sim, 7 sources):

| Window | mean ω | max std (which src) |
|---|---|---|
| 0.5–1s | 0.995–0.997 | 0.00177 (ES3) |
| 1–2s | 0.999 | 0.00165 (ES1) |
| 4–5s | 0.9997–0.9999 | 0.00053 (ES3) |
| 5–9s | 1.0000 | 0.00017 (ES4) |
| 9–10s | 1.0000 | 0.00013 (ES3) |

FFT peak power per source @ window [0.5, 1] s, dominant freq = 2 Hz across all 7 sources:

| Source | P @ 2 Hz |
|---|---|
| G1 | 0.000375 |
| G2 | 0.000309 |
| G3 | 0.000511 |
| ES1 | 0.000607 |
| ES2 | 0.00293 |
| ES4 | 0.00357 |
| ES3 | 0.0107 |

The shared 2 Hz frequency is consistent with an electromechanical swing mode, but does NOT prove
H1-H4 are falsified — Bus 14/15 attachments could excite the same natural mode preferentially.
Hypothesis tests are needed before any verdict.

---

---

## §10 Optimization Trail

This section captures performance and physics-preservation decisions made during Phase 1.

**FastRestart Viability (2026-05-03)**:
- Test: `probes/kundur/spike/test_fastrestart_v3_discrete.py`
- Physics preservation: rel err 2.46e-08 (off vs on-repeat) << 1e-5 tolerance
- Wall-clock benefit: 1.5× per-reset speedup (off-1=6.75s, off-2=1.78s warm, on-repeat=1.16s)
- Param-tune consistency: rel err 8.9e-06 on M_1 change (solver propagates correctly)
- Status: **FR_VIABLE** — ready for opt-in integration via `BridgeConfig.fast_restart` flag (default off, waiting for Phase 1.4+ integration)
- Constraint: All optimizations must preserve paper-grade physics per `feedback_optimization_no_perf_regression.md`

*end — Phase 1 progress + next steps as of 2026-05-03 EOD.*
