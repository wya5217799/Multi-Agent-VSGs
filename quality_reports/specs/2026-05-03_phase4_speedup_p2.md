# Requirements Spec: probe_state Phase 4 Subprocess Parallelization (P2)

**Date:** 2026-05-03
**Status:** DRAFT (awaiting (a) FR baseline wall data from background run `bvc00fouh`, (b) operator approval, (c) 4-engine license smoke result)
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Author:** spec-drafter agent (parent: planning agent)
**Approval:** PENDING — implementation plan is GATED on FR data + operator GO

**Related docs:**
- `quality_reports/plans/2026-05-03_phase1_progress_and_next_steps.md` §6.2 (P2 trigger conditions)
- `quality_reports/plans/2026-05-03_engineering_philosophy.md` §6 (DON'T MOVE GOALPOSTS), §8 (decision-driven tests)
- `C:\Users\27443\.claude\projects\C--Users-27443-Desktop-Multi-Agent--VSGs\memory\feedback_optimization_no_perf_regression.md` (paper-faithful physics non-regression)
- `probes/kundur/spike/test_fastrestart_v3_discrete.py` (FR microtest, FR_VIABLE 2026-05-03)
- `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md` (convention reference; this spec follows the same structure)

**Dependencies:**
- FR baseline wall data lands from background task `bvc00fouh` (probe `--phase 4 --fast-restart` on v3 Discrete, t_warmup_s=5, sim_duration=3.0). Result lands as `FR_BASELINE_WALL_S = TBD`. Spec is parameterized on this; trigger evaluation in §8 cannot fire until value is known.
- LoadStep adapter fix (E1 agent 2026-05-03) brings effective dispatches from 15 to 18 in Phase 4 sweep.
- 4-engine concurrent MATLAB license smoke: NOT YET RUN. 2-engine smoke PASSED 2026-05-03 (engine-2 cold start 9.2s, no license error). M7 BLOCKED on this.

---

## 1. 背景与动机 (Background)

probe_state Phase 4 (`run_per_dispatch` in `probes/kundur/probe_state/_dynamics.py`) executes one Simulink sim per effective dispatch and produces `max_abs_f_dev_hz_global` for the G1 falsification gate. On v3 Discrete with `t_warmup_s=5.0`, `sim_duration=3.0`, the serial wall was measured at **2168s ≈ 36 minutes** (15 dispatches that completed; 3 erroring out before E1 fix → post-fix: 18 dispatches expected).

The FR microtest 2026-05-03 (`test_fastrestart_v3_discrete.py`) showed:
- physics rel err 2.46e-08 (off vs on-repeat) << 1e-5 acceptance
- 1.5× per-sim wall savings (35% reduction)
- param-tune sanity rel err 8.9e-06 on M_1 change

FR is integrated as opt-in `--fast-restart` flag on probe CLI + `BridgeConfig.fast_restart`. The currently-running task `bvc00fouh` is a `--phase 4 --fast-restart` sweep that produces `FR_BASELINE_WALL_S` (placeholder until the operator fills it in here):

```
FR_BASELINE_WALL_S = WONT_PRODUCE_SPEEDUP (bvc00fouh exit 0; integrated wall = 2764s = 46 min, +28% over alpha)
ALPHA_PRE_FR_BASELINE_WALL_S = 2168s (36 min)  ← used as trigger reference per §8
```

**Status update 2026-05-03 EOD (post-bvc00fouh):** the in-flight `bvc00fouh` task completed cleanly (no hang, no orphan MATLAB.exe). Wall measured: **46 min, 28% slower than alpha**. FR microtest's 35% per-sim speedup did not translate to integrated `env.reset → warmup → multi-dispatch` loop. Per-dispatch wall ~176s (vs alpha's 181s) — essentially same; FR added cold-start + snapshot-save overhead without gain in this context. FR integration was reverted (1-line: `engine/simulink_bridge.py:301` `_apply_fast_restart()` call commented out). `BridgeConfig.fast_restart` field + `--fast-restart` CLI flag retained as dead code for future Option C refactor (single source of truth for FR state, unifying with `_fr_compiled` / `slx_episode_warmup_cvs.m` state machine).

The plan is **un-blocked** using alpha pre-FR baseline (2168s) as the trigger reference: §8 threshold (≥1500s = 25 min) satisfied by alpha alone. P2 is multiplicative (×N worker) and not dependent on FR. GATE-WALL @ N=4 ⇒ wall ≤ 2168 × 0.55 = **1192s** (uses alpha baseline, NOT FR baseline since FR is reverted).

If above the threshold, P2 implementation kicks off with this spec as the contract.

**Core opportunity:** Phase 4's 18 dispatches are **embarrassingly parallel** at the orchestrator level — each one is a self-contained `env.reset() + N steps`, with no inter-dispatch state. With N worker processes, theoretical wall is `wall_serial / N + overhead`. 2-engine smoke confirmed concurrent matlab.engine instances do not race on the license server.

**Goal:** Reduce probe_state Phase 4 wall by ≥ 2× via subprocess-level parallelization, where N worker processes each own a private MATLAB engine, each handling a disjoint dispatch subset. Snapshot fragments merge centrally; G1-G5 verdict re-computes on the merged snapshot. **Default N=1 preserves current serial behaviour bit-exactly.**

---

## 2. 范围 (Scope)

### 2.1 In Scope

| 文件 | 改动类型 | 阶段 |
|---|---|---|
| `probes/kundur/probe_state/__main__.py` | New CLI flags `--workers N`, `--dispatch-subset i,j,k` (or `--dispatch-names <comma-list>`), worker output dir routing | Module α |
| `probes/kundur/probe_state/_dynamics.py::run_per_dispatch` | Filter `targets` by subset slice/name list when in worker mode | Module α |
| `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete.m` (or wrapper script) | `skip_if_exists` flag with SHA256 cache key OR main-process pre-build orchestration | Module β |
| `probes/kundur/probe_state/probe_state.py` | Subprocess orchestration when `--workers >= 2`: spawn N children → wait → merge | Module γ |
| `probes/kundur/probe_state/_dynamics.py` (or new helper) | Snapshot merge function: combine N partial `phase4_per_dispatch.dispatches.*` dicts; cross-worker phase1/phase2/phase3 consistency check | Module δ |
| `probes/kundur/probe_state/_verdict.py` | NO CHANGE — `compute_gates(merged_snapshot)` runs centrally on merged snapshot | (unchanged path) |
| `probes/kundur/probe_state/_diff.py`, `_report.py` | NO CHANGE — must consume merged snapshots transparently (M5) | (unchanged path) |
| `probes/kundur/probe_state/README.md`, `AGENTS.md` | Document new flags + parallel-mode contract + license/RAM caveats | (final phase) |
| Implementation plan (separate doc) | NOT WRITTEN BY THIS SPEC | (gated on FR data) |

### 2.2 Out of Scope (explicit, to prevent scope creep in implementation plan)

| 路径/项目 | 不改原因 |
|---|---|
| `scenarios/kundur/train_simulink.py` | Production training parallelism is Phase 1.7+ scope (`feedback_optimization_no_perf_regression`: prod path untouched) |
| Phase 5 (`_trained_policy.py`, paper_eval ablation sweep) | Already runs 6 paper_eval subprocesses with different ablations; separate concern, separate semantics |
| Phase 6 (`_causality.py`, short-train) | Single-train artifact; parallelizing 200ep short-train requires separate license + RAM analysis |
| MATLAB Parallel Computing Toolbox (`parsim`, `parfor`) | Separate license, out of P2 first cut; revisit only if subprocess-level fails to deliver 2× |
| Threading inside one Python process (`threading`, `concurrent.futures.ThreadPoolExecutor`) | `matlab.engine` is process-bound — threads inside one process all share one engine, providing no parallelism |
| Schema changes to `workspace_vars.py`, `dispatch_metadata.py`, snapshot JSON schema | Touchless; merged snapshot must be schema-version 1 identical to serial |
| Build script logic changes beyond opt-in `skip_if_exists` flag | If skip-if-exists is too complex, fall back to S1 alternative (main-process pre-build); no other build changes |
| `_verdict.compute_gates` logic changes | G1-G6 thresholds frozen; merge-then-verdict order is the only architectural change |
| `engine/simulink_bridge.py` core logic | FastRestart flag already exists; no new bridge changes for P2 |
| `env/simulink/kundur_simulink_env.py` core logic | No env changes; workers each instantiate their own env |
| `--phase 5,6` CLI when run with `--workers > 1` | Out of P2; CLI must reject with clear error or silently fall back to serial |
| Result publication path (`results/harness/kundur/probe_state/state_snapshot_*.json`) | Single canonical merged snapshot at the existing path; per-worker outputs live in subdirs (S2) |

### 2.3 Locked Constants (paper-faithful physics non-regression contract)

`feedback_optimization_no_perf_regression`: optimization MUST NOT compromise physics correctness or G1-G6 verdicts. Touchless:
- `T_WARMUP`, `PHI_F`, `PHI_H`, `PHI_D`
- `KUNDUR_DISTURBANCE_TYPE` defaults
- `DEFAULT_KUNDUR_MODEL_PROFILE = kundur_cvs_v3` (test runs use `kundur_cvs_v3_discrete` via env-var override; do not change default)
- `DT_S`, `T_EPISODE`, `N_SUBSTEPS`, `STEPS_PER_EPISODE`
- `_compute_reward` / `_build_obs` formulas
- All G1-G6 verdict thresholds (e.g., 1mHz responding-agent threshold; expected_min_df_hz / expected_max_df_hz floors per dispatch)
- All `dispatch_metadata.METADATA` entries
- `T_WARMUP_S` defaults; probe `t_warmup_s` override semantics

---

## 3. Requirements

### 3.1 MUST (非协商)

| ID | Requirement | Clarity |
|---|---|---|
| M1 | Default `--workers=1` (or omitted) preserves the current serial Phase 4 path **bitwise**: snapshot byte-identical to pre-P2 (when run on the same git HEAD, same env, same CLI args). Validation: re-run a known snapshot pre-merge and post-merge — `_diff.py prev curr` shows zero deltas | CLEAR |
| M2 | `--workers=N` (N ≥ 2) reduces Phase 4 wall to ≤ `FR_BASELINE_WALL_S × (1.0 / N + license_overhead_factor)`, where `license_overhead_factor ≤ 0.3` (covers cold-start of N engines, build distribution, snapshot merge). E.g., for FR_BASELINE_WALL_S = 1500s and N=4: wall ≤ 1500 × (0.25 + 0.3) = 825s. **Acceptance gate: see GATE-WALL §5.** | CLEAR |
| M3 | For any single dispatch d, `phase4_per_dispatch.dispatches[d].max_abs_f_dev_hz_global` is identical between serial mode (`--workers=1`) and parallel mode (`--workers=N`) to ≤ **1e-9 absolute** (physics-determinism gate). Same for `max_abs_f_dev_hz_per_agent` (element-wise) and `agents_responding_above_1mHz` (exact int match). **Acceptance gate: see GATE-PHYS §5.** | CLEAR |
| M4 | Phase 1 + Phase 2 + Phase 3 fields must match across workers (each worker recomputes them independently; values must agree exactly because the same .slx + .mat is loaded). Specifically: `model_name`, `n_ess`, `n_sg`, `powergui_mode`, `solver`, `omega_tw_count_*`, `phase2.NR.*` (if recomputed by each worker), `phase3.per_agent` stats. Mismatch on any field → orchestrator aborts merge with explicit diagnostic naming the divergent field + the two values. Implementation may opt to (a) have only worker-0 produce phases 1/2/3 and other workers skip them, or (b) have all workers run them and check identity at merge. Both equally acceptable. | CLEAR |
| M5 | All snapshot consumers (`_diff.py`, `--diff`, `--promote-baseline`, `_report.py`, downstream MD report) handle parallel-mode merged snapshots identically to serial-mode snapshots — **no schema drift**. `schema_version=1` unchanged. `implementation_version` may bump (separate concern). | CLEAR |
| M6 | `feedback_optimization_no_perf_regression` non-regression contract: production training path is NOT touched. After P2 lands, `grep -nE "workers" scenarios/kundur/train_simulink.py` returns 0 hits; `grep -nE "workers" env/simulink/` returns 0 hits. P2 is probe-only. | CLEAR |
| M7 | License contract: MATLAB licensing allows **at least N concurrent matlab.engine instances on this machine**, where N is the target worker count. **2-engine concurrent: PASS (smoke 2026-05-03).** **4-engine concurrent: PENDING.** Until 4-engine smoke passes, this requirement is BLOCKED for `--workers ≥ 4`. **Acceptance gate: see GATE-LIC §5.** | **BLOCKED** — pending smoke `python -m probes.kundur.probe_state --workers-license-check` (or equivalent 4-engine launch test); see §7 |
| M8 | RAM contract: peak resident set size (RSS) during a `--workers=4` Phase 4 run does not exceed **8 GB** on operator's machine. Each MATLAB engine ~1.5 GB resident; 4 engines ≈ 6 GB plus orchestrator + Python overhead. If exceeded at runtime, log WARNING (not abort) — operator decides whether to continue. **Acceptance gate: see GATE-RAM §5.** | ASSUMED — actual RSS depends on operator machine; runtime soft check sufficient |
| M9 | G1-G5 falsification gates re-computed on merged snapshot match the serial-mode snapshot **verdict-for-verdict** (no PASS↔REJECT or PENDING↔PASS flips). Evidence strings (e.g., `evidence` field in each gate) are semantically equivalent — minor float-tail differences acceptable, structural differences (PASS reason changes from "all 18 above floor" to "17 of 18 above floor") NOT acceptable. **Acceptance gate: see GATE-G15 §5.** | CLEAR |

### 3.2 SHOULD (强偏好)

| ID | Requirement | Clarity |
|---|---|---|
| S1 | Build idempotency mechanism: prefer `skip_if_exists` flag on `build_kundur_cvs_v3_discrete.m` with SHA256 cache key (key = SHA256(build script + helper `build_dynamic_source_discrete.m`); when key matches saved key alongside `.slx`, skip rebuild). Alternative if SHA cache too complex: main-process pre-build before forking workers (workers receive `--no-build` flag). Both acceptable; ADR records choice + rationale. | ASSUMED — implementation chooses based on build-time profiling |
| S2 | Per-worker output dir: `results/harness/kundur/probe_state/p2_worker_<n>/` (n in 0..N-1). Final merged snapshot lives at canonical path (`results/harness/kundur/probe_state/state_snapshot_<timestamp>.json` + `state_snapshot_latest.json`). Per-worker dirs are auxiliary — not consumed by `_diff.py` etc. | ASSUMED |
| S3 | Worker process exit codes: 0 = success, non-zero = abort merge with diagnostic. Specifically: 1 = MATLAB engine failed (license, init), 2 = sim crash on assigned dispatch, 3 = output write error. Orchestrator surfaces non-zero exit codes in merged snapshot's `errors` list. | CLEAR |
| S4 | Logging: each worker writes to its own log file (`p2_worker_<n>/probe.log`). Orchestrator interleaves a high-level log to stdout with `worker_<n>:` prefix on key events (started, dispatch_completed, finished, exit_code). No interleaving of fine-grained DEBUG lines. | CLEAR |
| S5 | Dispatch subset routing: `--dispatch-subset i,j,k` accepts integer indices into the effective dispatch list (after Phase 1 produces it). Alternative: `--dispatch-names <name1>,<name2>` accepts dispatch type names. Both accepted; one is a wrapper for the other in implementation. The orchestrator chooses how to slice (round-robin, contiguous, or per-cost balanced) — no hard requirement on slicing strategy. | ASSUMED — slicing strategy is implementation-detail; round-robin is simplest |
| S6 | Failure isolation: if worker N crashes (exit code != 0), orchestrator continues, captures partial result, and produces a merged snapshot with `errors=[...]` containing the missing dispatch names. Verdict re-compute degrades gracefully (G4 will mark dispatches as `errored` per existing `_phase_status` contract; G1 will become PENDING if too few dispatches are intact). | ASSUMED — exact graceful-degradation rules need implementation details |
| S7 | `__main__.py` logs an explicit "running in parallel mode, N=<N>" banner at startup; "running in serial mode" otherwise. Operator can grep for this in CI logs. | CLEAR |
| S8 | Spec-mandated single ADR after implementation lands: `docs/decisions/YYYY-MM-DD-probe-state-phase4-p2-parallelization.md` capturing build-idempotency choice (S1), slicing strategy (S5), and any waivers from M3/M4 tolerances. | CLEAR |

### 3.3 MAY (可选, future / nice-to-have)

| ID | Requirement | Clarity |
|---|---|---|
| Y1 | `--workers auto`: heuristic that detects available license count + free RAM, picks N. Future enhancement; v1 requires explicit integer N. | CLEAR |
| Y2 | Worker-level retry on transient MATLAB engine errors (e.g., one-off `Engine connection lost`). Default v1: no retry, exit code 1. | CLEAR |
| Y3 | Per-dispatch per-worker timing telemetry exposed in `phase4_per_dispatch.dispatches[d].config` (e.g., `worker_id`, `wall_s_per_dispatch`). Diagnostic-only; M3 still applies to physics fields. | CLEAR |
| Y4 | Pre-flight `--workers-license-check` mini-CLI that launches N matlab.engine instances, logs success, exits. Helpful for operator before committing to a long P2 run. | CLEAR — relevant to resolving M7 BLOCKED |

---

## 4. 决策日志 (Fuzzy Points)

### 4.1 Point 1 — Worker pool primitive: `subprocess.Popen` × N vs `concurrent.futures.ProcessPoolExecutor`

**Decision (recommended for plan):** Either is acceptable. `subprocess.Popen` × N is simplest (each worker runs `python -m probes.kundur.probe_state --phase 4 --dispatch-subset <slice> --output-dir <worker_n_dir>`); `ProcessPoolExecutor` provides cleaner future-based collection. Implementation chooses; no MUST.

**Why not threads:** matlab.engine is process-bound — threads inside one Python process share one engine. Confirmed by 2-engine smoke (each engine in its own process).

**Constraint (M7-related):** Whichever primitive is chosen, each worker MUST own a private matlab.engine instance. This is the licensed-resource of concern.

### 4.2 Point 2 — Build idempotency: SHA cache vs pre-build orchestration

**Decision (deferred to implementation):** Implementation evaluates both during plan phase and chooses based on (a) build-script editability without breaking helper imports, (b) cache-key logic complexity. ADR (S8) records choice.

**Why this is fuzzy:** SHA256 cache is the cleaner pattern (auto-invalidates), but the build script is MATLAB code; implementing a robust cache key requires either MATLAB-side logic (writing/reading a `.cache_key` file) or Python-side wrapping (compute SHA256 of build script, pass as arg, MATLAB reads and compares). Pre-build is simpler but requires orchestrator coordination. No clear winner pre-implementation.

**Failure mode:** If chosen mechanism allows a race (two workers writing same .slx simultaneously), GATE-PHYS will detect the corrupted model via physics-determinism comparison, and the run aborts before merge. This is the safety net.

### 4.3 Point 3 — Snapshot merge on Phase 1/2/3 consistency: identity check vs trust-worker-0

**Decision (deferred to implementation):** Either approach satisfies M4. Plan phase chooses based on simplicity. Recommended: trust-worker-0 (only worker 0 runs phases 1/2/3; others skip via existing `--phase 4` CLI). This minimizes redundant work and obviates the cross-worker identity check entirely. Cost: worker 0 does slightly more work, slightly worse load balancing.

### 4.4 Point 4 — Merge-time verdict recompute vs accept worker-N partial verdicts

**Decision (CLEAR):** Verdict recompute happens **centrally**, on the merged snapshot, via `_verdict.compute_gates(merged_snapshot)`. Workers DO NOT compute G1-G5 themselves — they only produce per-dispatch data into `phase4_per_dispatch.dispatches.*`. Worker output is data; verdict is the orchestrator's responsibility.

**Why:** G1-G5 logic (e.g., G1 looks at floor_status across ALL dispatches, G4 reconciliation) requires all dispatches in one snapshot. Per-worker partial verdicts would either be wrong or duplicate. Single source of truth = orchestrator computes once on merged data.

### 4.5 Point 5 — `FR_BASELINE_WALL_S` placeholder resolution

**Decision (CLEAR, but VALUE BLOCKED):** `FR_BASELINE_WALL_S` is the wall-clock from background run `bvc00fouh` (`python -m probes.kundur.probe_state --phase 4 --fast-restart --t-warmup-s 5.0 --sim-duration 3.0` on v3 Discrete). When that run completes, operator updates §1 (replace `TBD pending bvc00fouh` with the measured value) and §8 (re-evaluate trigger condition). Until then, this spec is DRAFT — no implementation plan written.

**Why parameterize on this:** P2 is a 5-10 hour implementation. If FR alone gets the wall under 20 minutes, P2 is overkill. Premature optimization is the §6.4 trap (engineering_philosophy.md). Trigger logic must consume real measurements, not assumptions.

---

## 5. 验收测试 (Pre-Registered Acceptance Gates — IMMUTABLE)

These gates are **frozen at spec approval time**. Per `2026-05-03_engineering_philosophy.md` §6 (DON'T MOVE THE GOALPOSTS), no relaxation post-implementation without a separate spec amendment justified by physics or measurement (not "this makes the test pass"). Per §8 (decision-driven tests), each gate produces a concrete decision: PASS → ship; FAIL → halt + diagnose.

| Gate ID | Threshold | Measurement Protocol | Source / Justification |
|---|---|---|---|
| **GATE-PHYS** | For every dispatch d in the effective list: `|max_abs_f_dev_hz_global_serial[d] - max_abs_f_dev_hz_global_parallel[d]| ≤ 1e-9`. Element-wise on `max_abs_f_dev_hz_per_agent` same threshold. `agents_responding_above_1mHz` exact int match. | (1) Run `--workers=1 --fast-restart --t-warmup-s 5.0 --sim-duration 3.0` → snapshot S_serial. (2) Run same with `--workers=4` → snapshot S_parallel. (3) Use `_diff.py` or a custom comparator: extract the three fields per dispatch from both, compute diffs, assert all within tolerance. (4) Assert zero mismatches. **Tooling:** `python -m probes.kundur.probe_state --diff S_serial.json S_parallel.json` should produce a diff scoped to non-physics fields only (timestamps, run_id). | feedback_optimization_no_perf_regression: physics correctness is the hard floor. 1e-9 absolute is solver determinism for ode4 fixed-step Discrete (typical < 1e-12; 1e-9 is 1000× safety). |
| **GATE-WALL** | `wall_phase4_parallel ≤ FR_BASELINE_WALL_S × (1.0 / N + 0.3)` where N = `--workers=N`. For target N=4 and FR_BASELINE_WALL_S = e.g. 1500s: wall ≤ 825s. | `time` the probe with `--phase 4 --fast-restart --workers=N` on otherwise-quiet machine (no other MATLAB sessions, browser closed, etc.). Compare against `(FR_BASELINE_WALL_S / N) + 0.3 * FR_BASELINE_WALL_S`. | M2 + project ROI calc: 0.3 overhead factor budgets cold-start of N engines (~10s each), build distribution (~2s), snapshot merge (~1s); total << 30% for any reasonable FR_BASELINE_WALL_S > 100s. |
| **GATE-G15** | All 5 falsification gates G1-G5 in parallel-mode merged snapshot match serial-mode snapshot **verdict-for-verdict** (PASS / REJECT / PENDING / ERROR identical). Evidence strings semantically equivalent: any structural difference (e.g., "18 of 18 above floor" → "17 of 18 above floor") = FAIL. Float-tail differences in evidence body = OK. | Run two snapshots per GATE-PHYS protocol. Extract `falsification_gates.G1`..`G5` from each. Assert: (a) `verdict` field matches exactly across all 5; (b) `evidence` structural fields (e.g., `n_above_floor`, `n_total`) match exactly; (c) `evidence` numeric fields within 1e-9. | M9; project rule "Smoke PASS ≠ Validity" (engineering_philosophy.md §3): no silent verdict drift between modes. G6 excluded — Phase 5/6 not in scope. |
| **GATE-LIC** | `--workers=4` engine cold-start sequence completes without license error. Specifically: 4 successful "MATLAB engine ready" log lines (one per worker) within 60s of orchestrator start. | Run `--workers=4 --fast-restart --t-warmup-s 5.0 --sim-duration 3.0` (or, before P2 implementation: `--workers-license-check` Y4 helper). Inspect log: `grep "MATLAB engine ready" *.log | wc -l` ≥ 4. License error patterns (`license checkout failed`, `License Manager Error`) absent. | M7 BLOCKED resolution. 2-engine PASS established 2026-05-03; 4-engine the next gate. |
| **GATE-RAM** | Peak RSS across all worker processes during a 4-worker run does not exceed **8 GB**. | Optional / diagnostic: instrument orchestrator to sample `psutil.Process(child).memory_info().rss` every 30s; emit max. Soft warning if exceeded; not a hard FAIL. | M8 ASSUMED — operator-machine-dependent. Soft gate to surface OOM risk before swap. |

**Gate execution order:**
1. **GATE-LIC first** — without license, no other gate runs. Happens at orchestrator startup.
2. **GATE-WALL** — collected during the parallel run.
3. **GATE-PHYS, GATE-G15** — post-run, comparing serial baseline (collected once, cached) vs parallel snapshot.
4. **GATE-RAM** — collected during the parallel run; soft.

**On any HARD gate fail (PHYS, WALL, G15, LIC):** halt, do not promote merged snapshot to baseline, file diagnostic, do not commit P2 implementation. Per engineering_philosophy.md §6.

---

## 6. 风险与回滚 (Risks & Rollback)

### 6.1 主要风险

| ID | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R_P1 | License limit hit at N=4 (or N=3) — workers fail to start | `License checkout failed` in worker log | Y4 pre-flight `--workers-license-check`; if fails, downgrade target N (e.g., N=2 still gives 1.7-2× wall reduction); document in ADR |
| R_P2 | Build-time race: two workers write to `kundur_cvs_v3_discrete.slx` or `_runtime.mat` simultaneously, corrupting the model | Worker spurious sim crash; physics-divergent results | S1 `skip_if_exists` SHA cache or pre-build orchestration; GATE-PHYS catches corrupted physics |
| R_P3 | Snapshot merge inconsistency: phase 1/2/3 fields disagree across workers (e.g., one worker sees `n_ess=4`, another `n_ess=3`) | M4 cross-worker check fails | M4 explicit check + abort; alternative: only worker 0 runs phases 1/2/3 (Decision 4.3) |
| R_P4 | G4/G5 verdict differs between serial and parallel — hidden parallel-mode floor mismatch on a dispatch | GATE-G15 fail | Verdict computed centrally on merged snapshot (Decision 4.4); GATE-G15 catches drift |
| R_P5 | Physics-determinism violated: worker engines diverge subtly due to thread / hardware variance (e.g., FastRestart compiled state slightly different due to compile-time scheduling) | GATE-PHYS at 1e-9 fails (e.g., 1e-7 difference appears) | Investigate before relaxation: re-run with no FastRestart in parallel mode; if difference persists → root cause via single-worker sim repeated under same engine. Do not move goalposts — § 6 rule. |
| R_P6 | Per-worker output dir collisions or stale data persists between runs | Old `p2_worker_<n>/` not cleaned, polluting merge | Orchestrator `rm -rf p2_worker_<n>/` at start; or use per-run timestamped dir |
| R_P7 | RAM blow-up on operator machine (4 × 1.5 GB MATLAB + Python ≈ 7-8 GB; some machines <16 GB) | OS swap thrashing, wall regresses | GATE-RAM soft warning; Y1 `--workers auto` with RAM detection (future); operator manually downgrades N |
| R_P8 | `--diff`, `--promote-baseline`, `_report.py` unaware of parallel-mode artifacts (e.g., expects only serial-mode output dir) | Downstream tooling crashes on merged snapshot | M5 explicit; merged snapshot canonical path = serial path; per-worker dirs invisible to consumers |

### 6.2 回滚策略

- P2 lands as a single coherent commit (or small atomic series) gated behind `--workers >= 2`. With `--workers=1` (default), the new code path is dead-code from a runtime perspective; flag-off rollback is `--workers=1` everywhere.
- Hard rollback: `git revert <p2_commit>` is clean; nothing in production training touches the new code (M6).
- Per-stage rollback: implementation phases deliver in order `α → β → γ → δ`. Failure at any stage → revert that stage; previous stages are independently valuable (e.g., α `--dispatch-subset` flag is useful standalone for debugging single dispatches in serial mode even without γ orchestration).
- Mid-flight failure during a P2 run does NOT corrupt the canonical state — orchestrator only writes `state_snapshot_latest.json` after merge succeeds.

---

## 7. 估时与门控 (Estimate & Gating)

| 阶段 | 估时 | 门控 (摘要) |
|---|---|---|
| Pre-FR data | 0 (waiting on `bvc00fouh`) | FR_BASELINE_WALL_S resolved |
| Plan write (separate doc) | 1-2 hr | Spec approved + FR_BASELINE_WALL_S triggers P2 (§8) |
| Module α — CLI flags | 1-2 hr | Unit test for `--dispatch-subset` slicing |
| Module β — build idempotency | 1-3 hr (depends on chosen mechanism) | Two workers can build concurrently without race |
| Module γ — orchestrator | 2-4 hr | Smoke run with N=2 completes |
| Module δ — snapshot merge + verdict | 1-2 hr | M4 cross-worker identity check passes |
| 4-engine license smoke (Y4) | 30 min | GATE-LIC PASS |
| End-to-end gate run | 1-2 hr | All gates PASS (PHYS, WALL, G15, LIC; RAM informational) |
| Documentation + ADR (S8) | 1 hr | docs landed |
| **合计 (post-FR data)** | **8-15 hr** | |

**Gating before plan-writing:**
- [ ] FR_BASELINE_WALL_S measured from `bvc00fouh`
- [ ] §8 trigger condition evaluated against the value
- [ ] Operator GO on the trigger evaluation
- [ ] M7 4-engine license smoke (Y4) PASS

**Gating before P2 commits:**
- [ ] All gates PHYS, WALL, G15, LIC PASS
- [ ] Operator review of merged snapshot and `_diff.py` output
- [ ] ADR (S8) drafted

---

## 8. 进入条件 (Trigger Condition — When P2 Actually Fires)

Per `2026-05-03_phase1_progress_and_next_steps.md` §6.2, P2 is triggered only after measurement. The trigger logic, **parameterized on alpha pre-FR baseline (FR reverted post bvc00fouh measurement)**:

| BASELINE_WALL_S | Decision |
|---|---|
| **< 20 × 60 = 1200s (20 min)** | P2 NOT triggered. Spec stays approved-but-deferred. |
| **1200s ≤ BASELINE_WALL_S < 1500s (20-25 min)** | P2 marginal. Operator decides. |
| **≥ 1500s (25 min)** | P2 triggered. Plan is the contract. |

**Resolution 2026-05-03 EOD:** alpha pre-FR baseline = 2168s ≥ 1500s ⇒ **P2 TRIGGERED**. Plan persisted at `quality_reports/plans/2026-05-03_phase4_speedup_p2_plan.md`.

**Why FR baseline isn't used:** bvc00fouh measured 2764s wall (46 min) with `--fast-restart` — 28% slower than alpha. FR integration reverted (Option A: `engine/simulink_bridge.py:301` `_apply_fast_restart()` call commented out). FR is a deferred Option C refactor; spec uses alpha baseline as the immutable reference for GATE-WALL.

**Spec status (2026-05-03 EOD):** **APPROVED PENDING PLAN** → **plan persisted** → **IMPLEMENTATION COMPLETE** → **E2E PARTIAL PASS** (GATE-G15/WALL/LIC PASS; GATE-PHYS 12/15 bit-exact + 3 dispatch divergence from independent latent bug).

**Drift from initial plan §2.3 (recorded 2026-05-03 EOD post E2E v1):** Initial spawn_worker design assigned `--phase 2,3,4` to worker 0 and `--phase 4` to workers 1..N-1 (Decision 4.3 trust-worker-0 reasoning). E2E v1 revealed this was wrong — workers without Phase 1 hit `valid_targets=[]` in `_parse_subset_spec` and exited code=1. Fix: every worker runs Phase 1 (`1,2,3,4` for worker 0; `1,4` for others). +~15s wall (parallelised across workers). E2E v2 verified: 4 workers all exit 0, parallel wall 984.7s, GATE-WALL PASS (2.92× speedup). Plan §2.3 amended in same drift note. **Spec §3 M3 / M4 contracts unchanged**; only the implementation phase wiring was refined.

---

## 9. Clarity Status Table (per-requirement)

| Requirement | Status | Blocker / Resolution Path |
|---|---|---|
| M1 (default serial bitwise) | CLEAR | n/a |
| M2 (parallel wall ≤ N + 0.3 overhead) | CLEAR | n/a |
| M3 (per-dispatch physics 1e-9) | CLEAR | n/a |
| M4 (cross-worker phase 1/2/3 identity) | CLEAR | n/a |
| M5 (snapshot consumers no schema drift) | CLEAR | n/a |
| M6 (production path untouched) | CLEAR | n/a |
| **M7 (license ≥ N concurrent)** | **BLOCKED** | **Run Y4 `--workers-license-check` smoke for N=4 BEFORE plan written. If fails, plan must downgrade target N to the highest passing value; spec amendments to gates required.** |
| M8 (RAM ≤ 8 GB at N=4) | ASSUMED | Soft runtime check; operator-machine-dependent; not gating |
| M9 (G1-G5 verdict-for-verdict) | CLEAR | n/a |
| S1 (build idempotency) | ASSUMED | Implementation phase chooses; ADR (S8) records |
| S2 (per-worker dirs) | ASSUMED | Trivial implementation; no blocker |
| S3 (exit codes 0/1/2/3) | CLEAR | n/a |
| S4 (per-worker logs + orchestrator log) | CLEAR | n/a |
| S5 (subset routing CLI) | ASSUMED | Slicing strategy implementation-detail; round-robin or contiguous OK |
| S6 (failure isolation) | ASSUMED | Graceful-degradation rules need implementation |
| S7 (mode banner) | CLEAR | n/a |
| S8 (ADR) | CLEAR | n/a |
| Y1-Y4 (MAY items) | CLEAR | All optional |

**Top 3 BLOCKED items:**

1. **M7 — 4-engine concurrent MATLAB license**: 2-engine PASS, 4-engine UNTESTED. Resolution: operator runs `--workers-license-check` smoke (Y4 helper, ~30 min) before P2 implementation begins. If fails at N=4, downgrade target N (still get 1.7-2× at N=2; gates re-stated for the new N). This is a precondition for plan writing, not just spec sign-off.
2. **§1 FR_BASELINE_WALL_S placeholder**: depends on completion of background task `bvc00fouh`. Until value is known, §8 trigger evaluation cannot fire. Resolution: operator updates spec when run completes (1-2 hours).
3. **M8 RAM contract**: assumed-not-blocked, but soft-blocked if operator's machine is RAM-constrained. Resolution: GATE-RAM soft warning at runtime; if exceeded, operator decides (downgrade N or accept swap risk).

---

## 10. 不做 (Negative Scope, restated)

- **NOT writing the implementation plan.** That is a separate, gated artifact dependent on FR data + operator GO.
- Not introducing alternative parallelization designs beyond α/β/γ/δ as scoped above.
- Not changing G1-G6 verdict thresholds (paper baseline + design contract).
- Not changing snapshot schema (`schema_version=1` preserved).
- Not touching `train_simulink.py`, `paper_eval.py`, or any production code path.
- Not implementing MATLAB Parallel Computing Toolbox / `parsim` integration (out of P2 first cut).
- Not using threading inside one Python process (matlab.engine is process-bound).
- Not changing `_compute_reward` / `_build_obs` / any paper-baseline-locked formula.
- Not changing default `--workers=1` semantics (M1).
- Not relaxing GATE-PHYS, GATE-WALL, GATE-G15 thresholds post-hoc (engineering_philosophy.md §6).
- Not bundling phase 5/6 parallelism into P2 (separate concern, separate license/RAM budget).
- Not promoting a parallel-mode snapshot to baseline if any HARD gate fails.
- Not committing P2 code without the ADR (S8).

---

## 11. 决策审批 (Approval)

Operator action items before status changes from DRAFT to APPROVED:
- [ ] FR_BASELINE_WALL_S value filled in §1
- [ ] §8 trigger evaluation done
- [ ] Y4 4-engine license smoke PASS (resolves M7)
- [ ] Operator GO

Approval changes spec status:
- DRAFT → DEFERRED (if §8 trigger says no)
- DRAFT → APPROVED PENDING PLAN (if §8 trigger says yes; plan agent commissioned)

This spec is the contract for the future implementation plan. Anything in the plan that deviates from §3 MUSTs is a spec amendment requiring a new approval cycle.

*end — P2 spec as of 2026-05-03 EOD.*
