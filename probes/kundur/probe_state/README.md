# probe_state — Kundur CVS Model State Probe

> Runtime ground-truth probe for the Kundur CVS Simulink power-system
> model. Replaces "infer from history verdicts" with "look at the model
> state right now". Outputs G1-G6 falsification gates + JSON snapshot
> + Markdown report.

---

## Doc map (read the right one)

| You are... | Read | Scope |
|---|---|---|
| an operator running the probe | **`USAGE.md`** | command workflows, when-to-run, troubleshooting |
| an AI agent / tool deciding what to run | **`AGENTS.md`** | decision tables, output contract, hard rules |
| a developer reading or modifying the package | **this file (`README.md`)** | design rationale, scope, schema layout, versioning |
| writing a brand-new phase / extension | this file + `docs/design/probe_state_design.md` | full design source |

**Cross-link discipline**: this file does NOT duplicate command examples
(use `USAGE.md`) and does NOT enumerate machine-parseable contracts
(use `AGENTS.md`). It explains *why* the probe is shaped this way.

---

## Identity

```
purpose:  capture runtime ground-truth of the active Kundur CVS Simulink model
mode:     read-only on env / engine / paper_eval (one CLI flag added to train_simulink.py)
output:   state_snapshot_<TS>.json + STATE_REPORT_<TS>.md
gates:    G1-G6 falsification verdicts (PASS / REJECT / PENDING)
```

Plans (executed):
- Phase A: `quality_reports/plans/2026-04-30_probe_state_kundur_cvs.md`
- Phase B: `quality_reports/plans/2026-05-01_probe_state_phase_B.md`
- Phase C: `quality_reports/plans/2026-05-01_probe_state_phase_C.md`
- V1 verdict: `quality_reports/phase_C_R1_verdict_20260501T074245.md`

Design source: `docs/design/probe_state_design.md` (§1-§10).

---

## Design principles (non-negotiable)

1. **discovery > declaration** — entities (n_ess / dispatch / config) are
   discovered at runtime from the IC JSON / `_DISPATCH_TABLE` / model
   blocks. No `n_ess = 4` hardcode.
2. **single source of truth** — dispatches come from
   `disturbance_protocols.known_disturbance_types()`; thresholds come
   from `probe_config.THRESHOLDS`; coverage cross-validated by
   `dispatch_metadata.coverage_check()` at probe time.
3. **versioned schema** — snapshot carries `schema_version` (data
   shape) AND `implementation_version` (algorithm), both enforced as
   additive only. See *Versioning* below.
4. **fail-soft per phase** — a single phase failure populates
   `phase.error` and continues; downstream Type B invariants SKIP
   instead of failing the whole pytest run.
5. **read-only on production** — must not edit `.slx` / IC JSON /
   `evaluation/paper_eval.py` / `env/` / `engine/`. The single
   exception is the D-minimal `--run-id` flag in
   `scenarios/kundur/train_simulink.py` (Phase C plan §2).
6. **probe measures, does not interpret** — the probe collects facts
   (G1-G6 verdicts + reason_codes + evidence + timestamps) and stops
   there. Anchor-unlock decisions, paper-alignment judgments, and
   cross-phase composition rules belong to consuming agents, not the
   probe. CLAUDE.md PAPER-ANCHOR HARD RULE references G1-G6 verdicts
   the probe produces; whether any given verdict set is "fresh enough"
   for an anchor unlock is the operator/agent's call, not encoded here.

Violating any of P1-P6 = design regression. Phase B/C plans §2 enumerate
allowed extensions.

---

## Phase layout

| Phase | Module | Snapshot key | Reads from |
|---|---|---|---|
| 1 — static topology | `_discover.py` | `phase1_topology` | MATLAB `find_system` + scenario config + IC JSON |
| 2 — NR / IC | `_nr_ic.py` | `phase2_nr_ic` | `scenarios/kundur/kundur_ic_cvs_v3.json` (file IO only) |
| 3 — open-loop | `_dynamics.py` | `phase3_open_loop` | 5 s sim, all disturbance amps = 0 |
| 4 — per-dispatch | `_dynamics.py` | `phase4_per_dispatch` | one sim per effective dispatch (12 in v3) |
| 5 — trained-policy ablation (Phase B) | `_trained_policy.py` | `phase5_trained_policy` | `paper_eval.py` subprocess × (N+2) runs |
| 6 — causality short-train (Phase C) | `_causality.py` | `phase6_causality` | `train_simulink.py` subprocess (φ_f=0) + paper_eval |
| (always) — verdict | `_verdict.py` | `falsification_gates` | computed from phase data |
| (always) — report | `_report.py` | (writes JSON + MD) | snapshot dict |

## Parallel Mode (P2 — 2026-05-03)

**Why it exists**: Phase 4 dispatch sweep takes ~36 min serial on v3 Discrete
(`sim_duration=3.0`, `t_warmup_s=5`). Parallel mode targets ≤ 1192s @ N=4
worker processes (3.5× speedup). Each worker owns a private MATLAB engine;
snapshots merge centrally.

**Design constraints** (from spec §3):
- M1: default `--workers=1` preserves serial behaviour bit-exact.
- M3: physics determinism @ 1e-9 absolute per dispatch (M3 GATE-PHYS).
- M5: schema_version=1 unchanged; merged snapshots consumed transparently by
  `_diff.py`/`_report.py`.
- M6: production training path (`scenarios/kundur/train_simulink.py`) untouched.
- M7: license requires N concurrent matlab.engine instances; smoke 2-engine PASS
  (2026-05-03); 4-engine PENDING.

**Module layout** (Decision refs):
- **α (CLI)**: `--workers N`, `--dispatch-subset SPEC` (`_subset.py`).
- **β (build)**: `_ensure_build_current` pre-build before forking workers
  (`_build_check.py`).
- **γ (orchestrator)**: subprocess.Popen × N, round-robin slicing
  (`_orchestrator.py`).
- **δ (merge)**: central verdict recompute on merged snapshot (`_merge.py`).

**Worker dir layout**: `results/harness/kundur/probe_state/p2_worker_<n>/`
(per-worker output; includes per-worker `state_snapshot_latest.json` +
`probe.log`). Canonical merged snapshot at the existing `state_snapshot_<TS>.json`
path.

**Phase wiring** (corrected 2026-05-03): worker 0 runs
`--phase 1,2,3,4` (full workflow); workers 1..N-1 run `--phase 1,4` (Phase 1
required to validate the subset spec via `_dynamics.run_per_dispatch`, which
resolves targets from `phase1_topology.dispatch_effective`). Skipping Phase 1 in
workers ⇒ `valid_targets=[]` ⇒ `_parse_subset_spec` raises SystemExit.

**Trust-worker-0** (Decision 4.3): phases 2/3 in merged snapshot come from
worker 0's output; merge does NOT cross-validate phase 1/2/3 across workers
(identical by construction since same .slx + IC JSON loaded).

**`parallel_metadata` snapshot key** (new with P2): under
`phase4_per_dispatch.parallel_metadata`, contains `n_workers / worker_subsets /
worker_meta / dropped_dispatches`. M5-compatible (additive only; schema_version
unchanged).

**Disabled phases**: `--workers > 1` incompatible with `--phase 5/6`
(out of P2 scope); raises SystemExit at CLI validation.

---

## Falsification gates

| Gate | Falsification hypothesis | PASS condition |
|---|---|---|
| G1 — signal | "no dispatch can excite ≥ 2 agents" | ≥ 1 dispatch with ≥ 2 agents responding > 1 mHz |
| G2 — measurement | "all 4 omega traces are aliased" | open-loop sha256 distinct across agents |
| G3 — gradient | "per-agent reward share is degenerate" | max-min r_f share > 5% × mean (some dispatch) |
| G4 — position | "dispatch site doesn't change mode shape" | ≥ 2 distinct responder signatures across dispatches |
| G5 — trace | "agent omega-std collapses to one number" | std diff across agents > 1e-7 pu (some run) |
| G6 — trained-policy | "policy is degenerate AND/OR φ_f penalty isn't causal" | G6_partial PASS (Phase B) + R1 PASS (Phase C) |

Gate verdicts ∈ {`PASS`, `REJECT`, `PENDING`, `ERROR`} (v0.5.0). Each
verdict dict also carries `reason_codes: list[str]` from a frozen
vocabulary in `probe_config.REASON_CODES`. Logic in `_verdict.py`. For
state-machine semantics (how AI / operator should route on each
verdict), see `AGENTS.md` §5.

**ERROR vs PENDING (v0.5.0)**: PENDING means data insufficient —
re-running the relevant phase resolves it. ERROR means a pipeline
failure (phase threw, subprocess crashed); re-running alone does not
self-heal. The distinction is enforced by `_verdict.py` and asserted
at the report layer.

---

## Module layout

```
probe_state.py        ModelStateProbe orchestrator + ALL_PHASES
__main__.py           CLI entry (--phase, --diff, --promote-baseline, ...)
probe_config.py       ProbeThresholds dataclass + IMPLEMENTATION_VERSION
_discover.py          Phase 1 (static) — MATLAB find_system + IC parse
_nr_ic.py             Phase 2 (NR/IC) — pure file IO
_dynamics.py          Phase 3+4 (open-loop + per-dispatch) — bridge.step
_trained_policy.py    Phase 5 (Phase B) — paper_eval ablation runs
_causality.py         Phase 6 (Phase C) — short-train + R1 verdict
_verdict.py           G1-G6 verdict logic (compute_gates entry)
_report.py            JSON dump + Markdown render
_diff.py              snapshot deep-diff CLI (F2 / G3)
dispatch_metadata.py  22-dispatch metadata table (mag / floor / source)
__init__.py           package exports + __version__
```

Tests:
- `tests/test_state_invariants.py` — Type A / Type B invariants (5+7)
- `tests/test_probe_internal.py` — pure-Python self-tests (~38)

---

## Versioning

Two independent version fields in every snapshot:

| Field | When to bump | What it gates |
|---|---|---|
| `schema_version` (int) | snapshot **data shape** changes (rename / drop field) | Old snapshots load only after migration; `--diff` warns |
| `implementation_version` (semver) | probe **algorithm** changes (verdict thresholds, discovery heuristics, formula edits) | Verdict numbers across versions need CHANGELOG context |

**Bump rules**:
- additive field add (e.g. Phase B / C added their phase keys) → no
  bump (schema stays = 1; impl stays unless verdict logic changed).
- threshold value change in `probe_config.ProbeThresholds` → impl
  bump (minor for one knob, major for whole-protocol shift).
- snapshot field rename or repurpose → schema bump + migration plan.

CHANGELOG lives in `probe_config.py::IMPLEMENTATION_VERSION` docstring
(rolling, last 5). Use `python -m probes.kundur.probe_state --diff
prev curr` to see version bumps highlighted.

---

## Boundary with adjacent systems

| External | Probe interaction |
|---|---|
| `evaluation/paper_eval.py` | consumed via subprocess + JSON output; never imported |
| `scenarios/kundur/train_simulink.py` | consumed via subprocess; one CLI flag added (`--run-id`, D-minimal) |
| `scenarios/kundur/disturbance_protocols.py` | imported for `known_disturbance_types()` (single source of truth for dispatches) |
| `scenarios/kundur/config_simulink.py` | imported for `PHI_F` / `DIST_*` / etc.; ENV-var override path used by Phase C |
| `scenarios/kundur/workspace_vars.py` | imported for `effective_in_profile` schema |
| `engine/matlab_session.py` | imported for Phase 1 dynamic discovery |
| `engine/simulink_bridge.py` | imported indirectly via `KundurSimulinkEnv` for Phase 3+4 sim |
| `utils/run_protocol.py::generate_run_id` | imported via train_simulink (no probe-side override) |

Probe writes ONLY under `results/harness/kundur/probe_state/` and (for
Phase C) `results/sim_kundur/runs/probe_phase_c_*/`. Production train
output (`results/sim_kundur/runs/kundur_simulink_*/`) is read for
checkpoint discovery (Phase B) and never modified.

---

## Where to find...

| You want | Look in |
|---|---|
| Run a specific workflow | `USAGE.md` §"5 个常用 workflow" |
| Decision table (intent → command) | `AGENTS.md` §3 |
| Snapshot JSON field schema | `AGENTS.md` §4 |
| Why G6 has two scopes | `_verdict.py::_g6_trained_policy` docstring + `AGENTS.md` §5 |
| What "spurious R1 PASS" means | `_causality.py::_compute_r1_verdict` docstring |
| Threshold defaults | `probe_config.py::ProbeThresholds` |
| Per-dispatch expected floor | `dispatch_metadata.py::METADATA[<name>]` |
| Plan or verdict context | `quality_reports/plans/` + `quality_reports/phase_C_R1_verdict_*.md` |

---

*end — `USAGE.md` for operators, `AGENTS.md` for AI, this file for designers.*
