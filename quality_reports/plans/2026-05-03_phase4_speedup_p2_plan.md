# Implementation Plan: probe_state Phase 4 Subprocess Parallelization (P2)

**Date:** 2026-05-03
**Status:** DRAFT — pending operator approval
**Branch:** `discrete-rebuild`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Spec:** `quality_reports/specs/2026-05-03_phase4_speedup_p2.md`
**Author:** planner agent (parent persists)

---

## §1 Overview

**Goal.** Reduce probe_state Phase 4 wall by ≥ 2× via subprocess-level parallelization, where N worker processes each own a private `matlab.engine` instance and handle a disjoint dispatch subset. Fragment snapshots merge centrally; G1-G5 verdict re-computes on the merged snapshot. Default `--workers=1` preserves current serial behaviour bit-exactly.

**Trigger evaluation.** Spec §1 had `FR_BASELINE_WALL_S = TBD pending bvc00fouh`. The in-flight task hung (5 orphaned MATLAB.exe; FR integration bug under separate debugger track). We use the **alpha pre-FR baseline = 2168s (36 min)** as the trigger reference. Per spec §8, `FR_BASELINE_WALL_S ≥ 1500s` triggers P2; **2168s ≥ 1500s ⇒ P2 TRIGGERED**. `FR_BASELINE_WALL_S` is a deferred secondary baseline — when FR debug lands, GATE-WALL acceptance can be retuned via spec amendment, but P2 plan writing does not block on it. **All §5 gates use the alpha 2168s baseline as the parallel-mode comparison**: GATE-WALL @ N=4 ⇒ wall ≤ 2168 × (0.25 + 0.30) = **1192s**.

---

## §2 Module Sequencing

### §2.1 Module α — `--dispatch-subset` + `--workers` CLI flags (no orchestration yet)

**Goal.** Add the two new argparse flags to `__main__.py`; teach `_dynamics.run_per_dispatch` to consume the subset filter. No subprocess machinery yet — α is a serial-mode-equivalent capability. With α alone, an operator can run `--phase 4 --dispatch-subset 0,3,7` and get a partial Phase 4 sweep that correctly populates only the subset of `dispatches.*` keys.

**Files modified.**
- `probes/kundur/probe_state/__main__.py` — insert two new argparse args between line 139 (`--fast-restart`) and line 145 (`--verbose`); thread them into `ModelStateProbe(...)` ctor at line 203-215. New CLI surface: `--workers N` (int, default 1), `--dispatch-subset SPEC` (str, default None where SPEC is comma-sep ints OR comma-sep names).
- `probes/kundur/probe_state/probe_state.py` — add two ctor fields after line 65 (`phase_c_train_timeout_s`): `workers: int = 1`, `dispatch_subset: tuple[int, ...] | tuple[str, ...] | None = None`. Surface them in `__post_init__` config block lines 80-95 (new `config["workers"] = ...`, `config["dispatch_subset"] = ...`).
- `probes/kundur/probe_state/_dynamics.py::run_per_dispatch` — at line 229-232 the `targets` list is built by intersecting `phase1_topology.dispatch_effective` with `KUNDUR_DISTURBANCE_TYPES_VALID`; insert subset filter immediately after line 232. New helper `_apply_dispatch_subset(targets, subset_spec)` colocated in `_dynamics.py` (above `_build_env`).

**Implementation steps.**
1. Define `_parse_subset_spec(spec: str, valid_targets: list[str]) -> list[str]` in `__main__.py` (or in a new tiny `_subset.py`). Accepts: `"0,3,7"` → indices into the (already filtered) `targets` list; or `"pm_step_proxy_random_gen,ccs_inject_g1"` → name list. Detect by `try: int(s)` per token. Return canonical name list.
2. Add `--workers` (int, default=1, validate `>= 1`) and `--dispatch-subset` (str, default=None) to argparse. Add help text noting subset spec semantics + mutual exclusion with `--phase 5,6` (raise `SystemExit` if `--workers > 1` AND `phases ∩ {5,6}` non-empty per spec §2.2).
3. In `__main__.py::main` after parsing phases (line 197), validate: `if args.workers > 1 and any(p in (5,6) for p in phases): raise SystemExit("--workers > 1 incompatible with --phase 5/6 (out of P2 scope)")`.
4. Pass `workers=args.workers` and `dispatch_subset=parsed_subset` into `ModelStateProbe(...)` ctor.
5. In `_dynamics.run_per_dispatch` (after line 232) apply the subset filter; record what was filtered into return dict as new key `subset_applied: tuple[str, ...] | None`.
6. Banner per spec S7: at orchestrator startup in `probe_state.run` (line 100, before phase loop), if `self.workers > 1`: `logger.info("running in parallel mode, N=%d", self.workers)`; else `logger.info("running in serial mode")`.
7. Log filter outcome: when subset is applied, log `Phase 4 subset filter: %d/%d dispatches retained` with both counts.

**Test strategy.**
- Unit test `tests/test_p2_dispatch_subset.py::test_parse_subset_int_indices` — pure-Python; valid_targets=["a","b","c","d"], spec="0,2" → ["a","c"]. No MATLAB.
- Unit test `test_parse_subset_names` — spec="b,d" → ["b","d"].
- Unit test `test_parse_subset_index_out_of_range` — spec="9" with 4 targets → `SystemExit` with descriptive message.
- Unit test `test_parse_subset_mixed_int_and_name` — spec="0,b" → ["a","b"] (canonicalise).
- Unit test `tests/test_p2_subset_cli_validation.py::test_workers_with_phase5_rejects` — `--workers 2 --phase 5` raises `SystemExit`.

**Acceptance gate dependencies.** Satisfies spec M1 (workers=1 default unchanged path), S5 (subset routing CLI), S7 (mode banner). Does NOT touch physics → GATE-PHYS / GATE-G15 vacuously pass for α.

**Rollback.** Single-file revert of `__main__.py` + `probe_state.py` + `_dynamics.py`. No subprocess infra to back out.

**Estimated hours:** **1.5 hr**.

---

### §2.2 Module β — Build idempotency

**Goal.** Ensure 2-4 worker processes each calling MATLAB do NOT race on rebuilding `kundur_cvs_v3_discrete.slx`. The bridge does not invoke build scripts (verified via grep: no matches for `build_kundur_cvs_v3_discrete` in `engine/simulink_bridge.py`); each env constructor calls `load_system` (line 300 of bridge), which assumes the .slx exists. Today's path: build is operator-manual, run-once. P2 risk: if any worker triggers an implicit rebuild (e.g., the .slx is stale), two simultaneous writes can corrupt it.

**Recommendation: option B (main-process pre-build) over option A (SHA cache).** Rationale:
- Build script `build_kundur_cvs_v3_discrete.m` is ~hundreds of lines of MATLAB; adding a SHA cache layer requires either MATLAB-side IO of a `.cache_key` file or a Python wrapper that computes SHA(build script + helper) and conditionally invokes MATLAB. Either is fragile.
- Pre-build is 1 line of orchestrator code: before forking workers, run `build_kundur_cvs_v3_discrete()` once via the main-process MatlabSession (or a session sentinel that confirms the .slx mtime is newer than build script mtime + helper mtime). Workers receive a `--no-build` flag (which is already implicit — they never trigger a build).
- Spec S1 explicitly allows pre-build: "Alternative if SHA cache too complex: main-process pre-build before forking workers (workers receive `--no-build` flag)."

**Files modified.**
- `probes/kundur/probe_state/probe_state.py` — new method `_ensure_build_current(self)` colocated near `_run_phase` (around line 142). Runs only when `self.workers > 1`; checks `<repo>/scenarios/kundur/simulink_models/kundur_cvs_v3_discrete.slx` mtime against build script + helper mtimes; if stale, calls `MatlabSession.get('default').eval('build_kundur_cvs_v3_discrete()', nargout=0)` once. Logged. Workers do not re-check.
- New tiny helper `probes/kundur/probe_state/_build_check.py` (10-20 lines) — a pure-Python `is_build_current(slx_path, dependencies: list[Path]) -> bool` (mtime comparison). Importable by tests.

**Implementation steps.**
1. Create `_build_check.py` with one function `is_build_current(slx_path, deps) -> bool`: returns True iff `slx_path.exists()` AND `slx_path.stat().st_mtime >= max(d.stat().st_mtime for d in deps)`.
2. In `probe_state.py::ModelStateProbe.run` (line 99), before the phase loop, gate on `if self.workers > 1: self._ensure_build_current()`. (Serial mode is unchanged → no risk of regression.)
3. `_ensure_build_current` reads the build deps from a hardcoded list (paths inside `scenarios/kundur/simulink_models/`): `build_kundur_cvs_v3_discrete.m`, `build_dynamic_source_discrete.m`, plus the IC JSON `scenarios/kundur/kundur_ic_cvs_v3.json`. If `is_build_current` returns False, call MATLAB to rebuild via `MatlabSession.get('default')` (no per-worker session is started yet — this happens BEFORE worker fork).
4. Defensive guard: if rebuild fails, raise; do not silently fork workers against a stale model.
5. For determinism / observability, log the .slx mtime + dep mtimes to stdout before and after.

**Test strategy.**
- Unit test `tests/test_p2_build_check.py::test_is_build_current_fresh` — create temp .slx newer than deps → True. No MATLAB.
- Unit test `test_is_build_current_stale_dep` — touch a dep file → returns False.
- Unit test `test_is_build_current_missing_slx` — delete .slx → False.
- Integration test (manual, gated by smoke phase): with `--workers=2` and an in-date .slx, verify `_ensure_build_current` does NOT trigger rebuild; with a manually-touched build script, verify it DOES rebuild exactly once.

**Acceptance gate dependencies.** Mitigates spec R_P2 (build race). Indirectly preserves GATE-PHYS (corrupt .slx → physics divergence). Does not satisfy a specific MUST/SHOULD ID by itself; supports all of them.

**Rollback.** Single-file revert; pre-build call is gated by `self.workers > 1` so reverting the gate makes pre-build dead code.

**Estimated hours:** **1.5 hr** (chosen mechanism is the simpler pre-build; ADR records the choice).

---

### §2.3 Module γ — Subprocess pool orchestrator + per-worker output dirs

**Goal.** When `--workers >= 2`, fork N worker processes each running `python -m probes.kundur.probe_state --phase 4 --dispatch-subset <slice> --output-dir <worker_n_dir>`. Wait for all; harvest their per-worker snapshots; pass to merge module δ.

**Decision (spec Decision 4.1):** use `subprocess.Popen` × N, NOT `concurrent.futures.ProcessPoolExecutor`. Rationale: workers are full Python invocations of `python -m probes.kundur.probe_state`, NOT in-process callables. Popen is the natural primitive; future-based collection adds no value when we're already shelling out. ADR records this.

**Decision (spec Decision 4.3):** use **trust-worker-0** for phases 2/3. Worker 0's output dir contains the phase 2/3 entries; the merge takes phases 2/3 from worker 0 verbatim.

**~~Initial design (FALSIFIED 2026-05-03 EOD by E2E v1):~~** workers 1..N-1 launched with `--phase 4` only. **This was wrong** — `_dynamics.run_per_dispatch` resolves `targets` from `probe.snapshot["phase1_topology"]["dispatch_effective"]` to validate the `--dispatch-subset` spec via `_parse_subset_spec`. Without Phase 1 in-worker, `valid_targets=[]` and every name in subset is rejected as unknown → `SystemExit`. All 4 workers exited code=1 in 139s with 0 dispatches done.

**Corrected design (2026-05-03 E2E v1 → v2 fix):** **Phase 1 runs in EVERY worker**. Phase 1 is cheap (~15s, MATLAB cold start dominated) and parallelises across workers, so adds ~15s wall not 60s.

| Worker | `--phase` arg |
|---|---|
| 0 | `1,2,3,4` (Phase 1 for subset validation; 2+3 for trust-worker-0; 4 for assigned subset) |
| 1..N-1 | `1,4` (Phase 1 for subset validation; 4 for assigned subset) |

**Cross-worker phase 1 identity**: still **NOT** validated explicitly (phases 1/2/3 are deterministic given the same .slx + IC JSON loaded by every worker). Merge takes phase 1 from parent (parent already ran it before forking) and phases 2/3 from worker 0.

**E2E v2 verdict (2026-05-03 EOD)**: 4 workers all exit_code=0, total wall 984.7s = 16.4 min, 2.92× speedup, all 15 dispatches completed, GATE-G15/WALL/LIC PASS. (GATE-PHYS partial — 12/15 bit-exact 1e-9, 3 LoadStep/hybrid dispatches diverge — separate latent serial-mode state-contamination bug exposed by P2; not P2-introduced.)

**Files modified.**
- `probes/kundur/probe_state/probe_state.py` — new method `_run_parallel(self, targets: list[str]) -> dict` (called from `run` when `self.workers > 1`). Splits `targets` into N round-robin slices; spawns N `subprocess.Popen` with stdout/stderr captured to per-worker log files; waits with timeout; collects per-worker `state_snapshot_latest.json`. Per-worker output dir = `self.output_dir / f"p2_worker_{n}"`.
- `probes/kundur/probe_state/probe_state.py` — modify `run` (line 98+): when `self.workers > 1`, after Phase 1 runs locally to produce `dispatch_effective` (Phase 1 is cheap, deterministic, and required for slicing), short-circuit Phase 4 into `_run_parallel`. The orchestrator process itself only runs Phase 1 directly; Phase 2/3 done by worker-0; Phase 4 done by all workers.
- New `probes/kundur/probe_state/_orchestrator.py` (50-80 lines) — pure-logic module containing `slice_targets(targets, n_workers, strategy='round_robin') -> list[list[str]]`, `spawn_worker(idx, subset, output_dir, base_args, env) -> subprocess.Popen`, and `wait_for_all(workers: list[Popen], timeout_s: int) -> list[int]`. Importable for unit testing.
- `probes/kundur/probe_state/__main__.py` — when `--workers > 1` is passed at CLI, the parent's `main()` falls through to the same `ModelStateProbe.run()` code path; the splitting happens inside `run()`. Workers themselves invoked with `--workers=1` (passed via subprocess argv, not inherited) so no recursion.

**Implementation steps.**
1. In `_orchestrator.py`, `slice_targets(targets, n)` returns N lists round-robin: `targets[0::n]`, `targets[1::n]`, etc. (S5 round-robin recommended; balance is fine for small N).
2. `spawn_worker` constructs argv: `[sys.executable, "-m", "probes.kundur.probe_state", "--phase", phases_for_worker, "--workers", "1", "--dispatch-subset", ",".join(slice), "--output-dir", str(worker_dir), ...inherit_other_args(base_args)]`. For worker 0: `phases_for_worker = "2,3,4"` (worker 0 also computes phases 2/3 — Phase 1 already ran in parent). For workers 1..N-1: `phases_for_worker = "4"`. `--no-mcp` not propagated (workers must have MATLAB).
3. Capture each worker's stdout/stderr to `worker_dir/probe.log` (S4); inherit env vars unchanged.
4. Parent `run()` waits for all `Popen.wait()` with timeout = `2 * FR_BASELINE_WALL_S` (defensive). On timeout, send SIGTERM to surviving workers and abort merge. On any non-zero exit code, capture exit code into `errors[]` per S3 (1=engine fail, 2=sim crash, 3=write error — via documented protocol for workers), and merge proceeds with partial data per S6.
5. After all workers exit, parent invokes module δ merge.
6. Per-worker dir cleanup: at start of `_run_parallel`, `shutil.rmtree(worker_dir, ignore_errors=True)` if it exists, then `mkdir(parents=True)`. Mitigates R_P6.
7. Logging interleave (S4): each worker `Popen.poll()` lifecycle event surfaces a single line via parent logger with `worker_<n>:` prefix at INFO level. Fine-grained DEBUG stays in per-worker log file.

**Test strategy.**
- Unit test `tests/test_p2_serial_compat.py::test_workers_1_unchanged` — runs `ModelStateProbe(..., workers=1)` against a stub Phase 4 (mock `_dynamics.run_per_dispatch` to return canned data); verify NO subprocess spawned, snapshot matches pre-P2 byte-identical.
- Unit test `tests/test_p2_orchestrator.py::test_slice_targets_round_robin` — slice_targets(["a","b","c","d","e"], 2) == [["a","c","e"],["b","d"]]. No subprocess.
- Unit test `test_slice_targets_n_greater_than_targets` — N=4, targets=["a","b"]: returns [["a"],["b"],[],[]] (empty workers OK; orchestrator should still spawn N processes — see §4 R_P3 mitigation).
- Integration test `probes/kundur/spike/test_p2_smoke.py::test_two_worker_smoke` — gated by MATLAB, N=2, full pipeline with a 2-dispatch effective set; verify both workers exit 0 and merged snapshot has 2 dispatch entries. Runs ~20-30 min wall (depending on FR state).

**Acceptance gate dependencies.** Satisfies M2 (parallel wall budget — measurable only end-to-end), S2 (per-worker output dir), S3 (exit codes), S4 (logging), S6 (failure isolation).

**Rollback.** `git revert` of γ commit removes `_orchestrator.py` and the `_run_parallel` method; α/β remain functional in serial mode. `--workers >= 2` becomes inert (falls back to serial path).

**Estimated hours:** **3 hr** (largest module by complexity).

---

### §2.4 Module δ — Snapshot merge + central verdict recompute

**Goal.** Combine N partial snapshots from workers into one canonical snapshot. Validate cross-worker phases 1/2/3 (trust-worker-0 simplifies this to "use worker 0's"). Pass merged snapshot through `_verdict.compute_gates`. Verify `_diff.py` consumes it transparently.

**Files modified.**
- New `probes/kundur/probe_state/_merge.py` (50-100 lines) — pure-logic module:
  - `merge_snapshots(parent_partial: dict, worker_snapshots: list[dict]) -> dict` — produces canonical merged snapshot.
  - `_validate_worker_consistency(snapshots) -> list[str]` — collects warnings, never aborts unless fatal.
- `probes/kundur/probe_state/probe_state.py` — `_run_parallel` returns the merged snapshot; `run()` then runs `_run_phase("falsification_gates", lambda probe: _verdict.compute_gates(probe.snapshot), self)` exactly as today (line 125-128). No verdict-logic change. `_report.write` (line 131) consumes the merged snapshot; produces single canonical snapshot at the existing path.
- `probes/kundur/probe_state/_diff.py` — verify NO change required. Spec M5 is a contract. **Plan task: write a regression test that loads a canned merged snapshot and runs `diff_snapshots(merged, merged) == 0` to confirm idempotent diff.**

**Merge algorithm.**
1. Start from `parent_partial` (contains phase1_topology + global metadata produced by orchestrator).
2. From `worker_snapshots[0]`, copy `phase2_nr_ic`, `phase3_open_loop` verbatim (trust-worker-0 per Decision 4.3).
3. For `phase4_per_dispatch`: take the parent's prep dict (defaults, skipped lists), then merge each worker's `phase4_per_dispatch.dispatches.*` map. No overlap by construction (subsets are disjoint round-robin). Detect overlap → raise.
4. Merge top-level `errors[]` lists (parent + all workers, deduplicated by `(phase, error)` tuple).
5. Add new merged-only key `phase4_per_dispatch.parallel_metadata` containing: `n_workers`, `worker_subsets` (the slice each worker got), `worker_exit_codes`, `wall_per_worker_s`. Y3 telemetry.
6. Validation step: assert `phase4_per_dispatch.dispatches.keys() == set(union of all worker subsets)`; if any expected dispatch missing → add to `errors[]` with reason "worker_<n> dropped dispatch <name>" per S6.

**Implementation steps.**
1. Create `_merge.py` with the merge function (pure dict operations, no IO).
2. Wire merge call into `_run_parallel` after worker collection.
3. Single canonical write through existing `_report.write` (line 131); merged snapshot lands at `state_snapshot_<ts>.json` + `state_snapshot_latest.json` per the existing path. **Per-worker dirs are NOT cleaned up by the orchestrator** — they persist as audit trail. README documents this.
4. Compatibility check for `_diff.py`: write `tests/test_p2_merge.py::test_diff_handles_merged` — load a real merged snapshot fixture, run `diff_snapshots(serial_baseline, merged_parallel)`, confirm only non-physics fields differ (timestamps, `parallel_metadata` key added). The new `parallel_metadata` key may surface as `ADDED` in diff output — that's expected and acceptable; document in `README.md`.
5. Write `tests/test_p2_merge.py::test_merge_disjoint_subsets_canonical` — synthesise 3 worker snapshots with disjoint dispatch sets; merge; assert canonical schema.
6. Write `tests/test_p2_merge.py::test_merge_overlap_raises` — 2 workers claim same dispatch name → ValueError.
7. Verdict recompute is a pre-existing flow (line 125-128); the orchestrator's only responsibility is to ensure `compute_gates(merged_snapshot)` runs, which it already does.

**Test strategy.**
- Unit tests above (no MATLAB).
- Integration test `probes/kundur/spike/test_p2_phys_consistency.py::test_serial_vs_parallel_phys` — runs serial first (cached fixture from pre-P2) vs parallel; for each dispatch, asserts:
  - `|max_abs_f_dev_hz_global_serial - max_abs_f_dev_hz_global_parallel| ≤ 1e-9` (M3, GATE-PHYS).
  - element-wise `max_abs_f_dev_hz_per_agent` within 1e-9.
  - `agents_responding_above_1mHz` exact equality.
- Integration test `test_p2_phys_consistency.py::test_g1_g5_verdict_match` — loads both snapshots' falsification_gates; assert `verdict` field matches across G1-G5 (M9, GATE-G15).

**Acceptance gate dependencies.** Satisfies M3 (per-dispatch physics 1e-9), M4 (cross-worker phases 1/2/3 — via trust-worker-0 path), M5 (snapshot consumers no schema drift), M9 (verdict-for-verdict).

**Rollback.** `git revert` of δ commit; γ workers will produce per-worker dirs but no merge — operator manually inspects per-worker dirs. Not catastrophic; acceptable mid-rollback state.

**Estimated hours:** **2 hr**.

---

## §3 Cross-Module Test Plan

| Test file | Test fns | MATLAB needed? | Est. runtime | Module |
|---|---|---|---|---|
| `tests/test_p2_dispatch_subset.py` | `test_parse_subset_int_indices`, `test_parse_subset_names`, `test_parse_subset_index_out_of_range`, `test_parse_subset_mixed`, `test_workers_with_phase5_rejects` | No | < 1s | α |
| `tests/test_p2_build_check.py` | `test_is_build_current_fresh`, `test_is_build_current_stale_dep`, `test_is_build_current_missing_slx` | No | < 1s | β |
| `tests/test_p2_orchestrator.py` | `test_slice_targets_round_robin`, `test_slice_targets_n_greater_than_targets`, `test_slice_targets_empty` | No | < 1s | γ |
| `tests/test_p2_serial_compat.py` | `test_workers_1_unchanged` (mocks Phase 4; verifies snapshot byte-identical to pre-P2) | No | < 1s | γ (M1 anchor) |
| `tests/test_p2_merge.py` | `test_merge_disjoint_subsets_canonical`, `test_merge_overlap_raises`, `test_diff_handles_merged` | No | < 1s | δ |
| `probes/kundur/spike/test_p2_smoke.py` | `test_two_worker_smoke` (N=2 first, gated by Y4 for N=4) | YES | 20-30 min | γ + δ E2E |
| `probes/kundur/spike/test_p2_phys_consistency.py` | `test_serial_vs_parallel_phys` (GATE-PHYS), `test_g1_g5_verdict_match` (GATE-G15) | YES | 60-90 min (serial + parallel runs) | δ E2E |

**Mock fixtures.** `tests/fixtures/p2_partial_worker_snapshot_<n>.json` — small JSON files with 1-2 dispatches each, used by `test_merge_*`. Generate by capturing from a real run once and committing.

---

## §4 Risk Register (Concrete Mitigation Sequencing)

| ID | Likelihood × Impact | Detection | Mitigation order (cheapest first) | Decision criterion |
|---|---|---|---|---|
| R_P5 — physics determinism violated at 1e-9 | MED × HIGH | GATE-PHYS in `test_p2_phys_consistency.py` | (1) Re-run with `--no-fast-restart` parallel (rules out FR compile-state divergence). (2) Single-worker repeat test (rules out parallel itself). (3) Compare floating-point env: `numpy.show_config()`, MATLAB `version -release`. | If 1e-9 violated AND non-FR also fails → halt P2, file root-cause spike. **Do NOT relax the threshold.** Per philosophy §6. |
| R_P1 — license limit hit at N=4 | HIGH × HIGH | Y4 pre-flight `--workers-license-check`; or first GATE-LIC run | (1) Y4 first (cheap, decisive). (2) If fail at N=4, downgrade to N=3 and retry. (3) If N=3 fails too, downgrade N=2 (already PASS); document in ADR. | If Y4 PASS at N=4 → proceed. If FAIL → set max N and update spec via amendment-not-relaxation. |
| R_P2 — build race | LOW × HIGH | GATE-PHYS catches corrupted .slx (physics divergent); spurious sim crash before that | (1) Module β pre-build (already in plan). (2) If race somehow happens, GATE-PHYS catches; halt and rebuild manually. | Pre-build is sufficient prevention; nothing to relax. |
| R_P7 — RAM blow-up | MED × MED | GATE-RAM soft warning during run | (1) Operator runs `psutil` baseline alone (cheap). (2) If exceeded at runtime, log WARNING (not abort, per M8); operator decides. (3) If repeated swap thrashing, downgrade N. | Soft gate; operator-machine-dependent. Spec amendment not needed. |
| R_P3 — phase 1/2/3 disagree across workers | LOW × HIGH | Trust-worker-0 short-circuits this entirely | (1) Trust-worker-0 (Decision 4.3 in spec) — by construction only worker 0 produces phases 1/2/3. (2) If we ever switch to all-workers-redundant-phase1/2/3, would need cross-worker identity check. | Trust-worker-0 is plan default; no detection required for v1. |
| R_P6 — per-worker dir collision / stale data | LOW × MED | `_run_parallel` `rm -rf p2_worker_<n>/` at start | Already mitigated; nothing additional. | n/a |
| R_P8 — `_diff` / `_report` aware of parallel | LOW × MED | `test_p2_merge.py::test_diff_handles_merged` integration test | Test catches before commit. New `parallel_metadata` key surfaces as `ADDED` in diff; document in README. | If diff trips on merged shape, ADD `_diff.py::_SUMMARISE_KEYS` entry for `parallel_metadata` (line 44 of `_diff.py`). |
| R_P4 — G4/G5 verdict drift | LOW × HIGH | GATE-G15 in `test_p2_phys_consistency.py` | Verdict computed centrally on merged snapshot (Decision 4.4) → by construction same input → same output. GATE-G15 confirms. | If verdict drifts, root-cause is upstream (R_P5 physics divergence); same response. |

**Top 3 by likelihood × impact: R_P1 (HIGH×HIGH), R_P5 (MED×HIGH), R_P7 (MED×MED).**

---

## §5 Implementation Order (Sequential vs Parallel Agent Dispatch)

| Phase | Modules / Tasks | Agents needed | MATLAB? | Est. wall |
|---|---|---|---|---|
| 1 | α + β in parallel | 2 executor agents (independent files) | No (coding only) | 1.5 hr (parallel max) |
| 2 | γ (depends on α: needs `--dispatch-subset` flag) + δ (depends on γ shape: needs worker output dir convention) | 2 executor agents — γ first then δ overlaps once γ skeleton lands | No (coding only) | 3 hr (γ critical path) + 2 hr (δ overlap) |
| 3 | Integration tests (all unit-level + fixture builds) | 1 tester agent | No | 1 hr |
| 4 | **GATE-LIC / Y4 4-engine license smoke** — once, sequential | 1 operator + 1 tester | YES (4 engines spawned) | 30 min |
| 5 | GATE-PHYS / GATE-WALL / GATE-G15 end-to-end | 1 tester (runs `--workers=1` then `--workers=4` sequentially) | YES (5 engines total: 1 baseline + 4 parallel) | 60-90 min |
| 6 | ADR + README updates + commit | 1 doc agent | No | 1 hr |

**Cannot parallelize Phase 4** (single license smoke must run alone) **or Phase 5** (sequential N=1 vs N=4 comparison).

**Parent agent dispatch sequence:**
1. Dispatch α + β agents in parallel (Phase 1).
2. Wait for both. Approve.
3. Dispatch γ (Phase 2). When γ ships skeleton + tests, dispatch δ in parallel.
4. Wait for both. Approve.
5. Dispatch tester agent (Phase 3). Approve.
6. **Operator gate**: run Y4 4-engine smoke. If FAIL, halt + amend spec (downgrade N). If PASS, proceed.
7. Dispatch tester agent for Phase 5. Approve.
8. Dispatch doc agent. Final commit.

---

## §6 Code Skeleton

See planner agent's full output for inline code skeletons covering:
- `__main__.py` — argparse flags `--workers`, `--dispatch-subset`
- `_dynamics.py` — `_apply_dispatch_subset` filter helper
- `_orchestrator.py` (NEW) — `slice_targets`, `spawn_worker`, `wait_for_all`
- `_merge.py` (NEW) — `merge_snapshots`
- `probe_state.py::ModelStateProbe.run` — parallel branch wiring

Each block marked `# IMPLEMENT IN MODULE α/β/γ/δ` so executor agents have clear scope.

---

## §7 ADR Stub (S8)

To be saved at `docs/decisions/2026-05-XX-probe-state-phase4-p2-parallelization.md` (post-implementation date).

**Decisions to record:**
1. Worker pool primitive: `subprocess.Popen` × N (over `ProcessPoolExecutor`)
2. Build idempotency: main-process pre-build (over SHA cache)
3. Slicing strategy: round-robin
4. Phase 1/2/3 strategy: parent runs phase 1; worker 0 runs phases 2/3; trust-worker-0 path
5. Verdict computation: centrally on merged snapshot
6. Gate waivers: none expected; GATE-PHYS at 1e-9 strict per philosophy §6

---

## §8 Estimate Reconciliation

| Module | Spec hour | Plan hour | Notes |
|---|---|---|---|
| α — CLI flags | 1-2 | **1.5** | Two argparse flags + small helper + 5 unit tests |
| β — build idempotency | 1-3 | **1.5** | Chosen pre-build (simpler of two options); mtime check + 3 unit tests |
| γ — orchestrator | 2-4 | **3.0** | Largest single module; subprocess pool + per-worker dirs + S2/S3/S4/S6 |
| δ — snapshot merge + verdict | 1-2 | **2.0** | Pure-logic merge + 3 unit tests + R_P8 _diff regression test |
| Y4 license smoke (4-engine) | 0.5 | **0.5** | Operator gate; 30 min observed |
| End-to-end gates (PHYS, WALL, G15, RAM) | 1-2 | **1.5** | Two probe runs sequential (~60-90 min wall) + diff inspection |
| ADR + README + docs | 1 | **1.0** | S8 ADR + README "parallel mode" section |
| **Total** | **8-15** | **11.0** | Within budget; no scope cut needed. |

**Scope cut if needed**: ship α + β + γ first as commit-1 (serial-mode-equivalent + subset flag + orchestrator skeleton with N=1 hard-coded enforcement); ship δ + license/gate runs as commit-2.

---

## §9 Operator Sign-off Checklist

| Phase | Operator confirms |
|---|---|
| Phase 1 (α + β) | Branch contains commits for α, β; unit tests pass; no MATLAB invoked |
| Phase 2 (γ + δ) | Branch contains commits for γ, δ; unit tests pass; no E2E run yet |
| Phase 3 (integration tests) | All `test_p2_*.py` unit tests pass; no MATLAB |
| **Phase 4 (Y4 license smoke)** | `--workers-license-check` (or 4-engine spawn smoke) PASS; 4 lines of "MATLAB engine ready" within 60s; no `license checkout failed` patterns. **Spec M7 unblocked.** |
| Phase 5 (end-to-end gates) | GATE-LIC PASS, GATE-WALL PASS (≤ 1192s for N=4 against 2168s alpha baseline), GATE-PHYS PASS (per-dispatch 1e-9), GATE-G15 PASS (verdict-for-verdict), GATE-RAM informational |
| Phase 6 (ADR + commit) | `docs/decisions/...-p2-parallelization.md` drafted; spec §11 approval checklist complete; PR ready |

---

## §10 Negative Scope (restated from spec §2.2 + §10)

- Not modifying `train_simulink.py`, `paper_eval.py`, or any production path (M6).
- Not changing `_verdict.compute_gates` logic.
- Not changing snapshot `schema_version=1`.
- Not threading inside one Python process (matlab.engine process-bound).
- Not implementing `parsim` / Parallel Computing Toolbox.
- Not relaxing GATE-PHYS / GATE-WALL / GATE-G15 thresholds post-hoc (philosophy §6).
- Not bundling phase 5/6 parallelism into P2.
- Not committing P2 without ADR (S8).

---

## §11 Drift Notes (spec vs current code)

1. Spec §1 placeholder `FR_BASELINE_WALL_S = TBD pending bvc00fouh` is **DEFERRED** (`bvc00fouh` hung; FR debug separate track). Plan substitutes alpha 2168s baseline; gate thresholds use it. **DRIFT FROM SPEC.** Spec amendment recommended at next revision.
2. Spec §3 M7 BLOCKED — Y4 4-engine license smoke is a **runtime** gate (Phase 4 of impl order), not authoring gate. Plan was authored anyway per user GO; smoke is mandatory before E2E gates run.
3. Plan introduces a new merged-snapshot key `phase4_per_dispatch.parallel_metadata`; spec §3 M5 says "schema_version=1 unchanged. implementation_version may bump." Adding a new key is consistent with M5 (schema is "additive-compatible"); plan flags an `implementation_version` bump (semver minor) for the implementer.

---

*end — P2 plan as of 2026-05-03 EOD. Approval gates spec §11.*
