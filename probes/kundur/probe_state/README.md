# probe_state — Kundur CVS model state probe (Phase A)

> CLAIM: usage doc. Source-of-truth = `probe_state.py` runtime behaviour.

Captures runtime ground truth for the active Kundur Simulink model — replaces
"reason from history verdicts + paper-claim CLAIM" with "look at the model
state right now". Analogous to a software test fixture + invariants.

## Quick start

```bash
PY="C:/Users/27443/miniconda3/envs/andes_env/python.exe"

# all phases (Phase A: 1=static, 2=NR/IC, 3=open-loop, 4=per-dispatch)
$PY -m probes.kundur.probe_state

# only the file-IO phases (no MATLAB engine)
$PY -m probes.kundur.probe_state --no-mcp

# only static topology
$PY -m probes.kundur.probe_state --phase 1
```

Outputs go to `results/harness/kundur/probe_state/`:
- `state_snapshot_<timestamp>.json` — schema_version=1, all phase data
- `STATE_REPORT_<timestamp>.md` — human-readable summary + G1-G5 verdict

## Phase map

| CLI `--phase` | Snapshot key            | Source                                           |
|---------------|-------------------------|--------------------------------------------------|
| `1`           | `phase1_topology`       | MATLAB find_system + get_param + config import   |
| `2`           | `phase2_nr_ic`          | `scenarios/kundur/kundur_ic_cvs_v3.json`         |
| `3`           | `phase3_open_loop`      | `SimulinkBridge` 5s sim, all disturbance amps=0  |
| `4`           | `phase4_per_dispatch`   | `SimulinkBridge` 5s sim per effective dispatch    |
| (always)      | `falsification_gates`   | computed from phase 3+4 data (G1-G5)             |
| (always)      | report writers          | JSON dump + Markdown render                      |

## Falsification gates (Phase A)

| Gate | Question | Logic |
|------|----------|-------|
| G1 — signal      | ≥ 1 dispatch produces ≥ 2 agents responding > 1 mHz?  | from phase4 |
| G2 — measurement | 4 agents have distinct sha256(omega trace) in open-loop? | from phase3 |
| G3 — gradient    | Per-agent r_f share max-min > 5% × mean across dispatches? | from phase4 |
| G4 — position    | SG-side dispatches produce different mode-shape signatures? | from phase4 |
| G5 — trace       | Some dispatch shows 4-agent omega-std diff > noise floor? | from phase3+4 |

Gate verdicts ∈ {`PASS`, `REJECT`, `PENDING`}. See `_verdict.py`.

## What the probe does NOT do (Phase A scope)

- Trained-policy ablation (Phase B)
- φ causal short-train (Phase C)
- Hook auto-trigger / skill packaging (Phase D)
- Modify build / `.slx` / IC / runtime.mat (read-only, plan §3)
- Extend the disturbance dispatch table (single source of truth =
  `scenarios.kundur.disturbance_protocols.known_disturbance_types`)

## Design rules (plan §3, MUST hold)

1. **discovery > declaration** — `n_ess` derived from MATLAB queries, not hardcoded.
2. **MCP-first** — reuse simulink-tools where possible; bridge for sim phases.
3. **single source of truth** — dispatch types from `_DISPATCH_TABLE.keys()`.
4. **versioned schema** — JSON has `schema_version`.
5. **fail-soft per phase** — one phase failure does not abort the others.
6. **read-only** — does not write base workspace vars or modify the `.slx`.

## Companion tests

Two test files (Plan §8 / §8.5):

```bash
# A. Regression invariants over the latest snapshot.
$PY -m pytest tests/test_state_invariants.py -v
#   Type A — data-independent (paper FACT + project contract): always assert
#            (skip ONLY when no snapshot yet)
#   Type B — phase-data-required (fail-soft compatible): SKIP when the
#            relevant phase is missing or errored

# B. Probe self-test — pure-Python, no MATLAB.
$PY -m pytest tests/test_probe_internal.py -v
#   Tests the probe's own logic (verdict, serializer, discovery pattern,
#   dispatch metadata coverage). MUST pass on any clean checkout.
```

Run after edits to
`scenarios/kundur/{disturbance_protocols,workspace_vars,config_simulink}.py`,
build scripts, or this probe package.

## Per-dispatch metadata

`probes/kundur/probe_state/dispatch_metadata.py` carries per-dispatch
defaults (magnitude, sim duration, family, expected behaviour). The
single source of truth for "which dispatches exist" remains
`scenarios.kundur.disturbance_protocols.known_disturbance_types()`; the
self-test `test_dispatch_metadata_coverage_against_known_types`
guarantees the metadata stays in sync with the dispatch table — adding
a new dispatch without a metadata row triggers a CI failure here.

## Known caveats

- `aggregate_residual_pu`: `kundur_ic_cvs_v3.json` does not record a single
  scalar residual. Probe synthesises one from `global_balance` (sum of
  `p_load + p_gen + p_wind + p_ess + p_loss` should be ≈ 0); see Phase 2 dump.
- Phase 4 uses the `SimulinkBridge` directly (not `KundurSimulinkEnv`) so the
  full SAC pipeline is not loaded. Disturbances are injected via workspace
  vars per `scenarios.kundur.workspace_vars` schema.
- MATLAB cold-start ≈ 20 s; allow ~25 s before Phase 1 starts producing
  output. Total wall time on a fresh engine ≈ 5-10 min for all phases.
