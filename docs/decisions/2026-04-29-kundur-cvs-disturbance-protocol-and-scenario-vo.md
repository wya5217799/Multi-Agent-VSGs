# Kundur CVS Disturbance Protocol + Scenario VO

## Status
Accepted (2026-04-29). Closes C1 + C4 of the algorithm-layer refactor
spec `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`.

## Context

Pre-refactor: `KundurSimulinkEnv._apply_disturbance_backend` was a
240-line god method handling 14 disturbance-type strings via cascaded
elif arms; per-episode disturbance flowed through 4 independent input
paths into the env (`_disturbance_type =` private mutation,
`apply_disturbance(magnitude=...)` direct call, `reset(options={...})`,
`KUNDUR_DISTURBANCE_TYPE` env-var). The same workspace-var families
(Pm-step, Pmg-step, LoadStep R, LoadStep CCS) were inlined repeatedly
across the elif arms; sign conventions and "silence other family"
responsibilities were buried in comments rather than typed contracts.

This decision records the seam introduced by C1 (DisturbanceProtocol)
and the value-object collapse introduced by C4 (Scenario VO), plus
the deferred boundary for C2 (BridgeConfig discriminated union).

## Decision

### C1 — DisturbanceProtocol seam

`scenarios/kundur/disturbance_protocols.py` exposes:

- `DisturbanceTrace` — frozen dataclass recording the exact
  `(workspace_var_name, value)` sequence written by one dispatch,
  for monitoring and tests.
- `DisturbanceProtocol` Protocol with method
  `apply(bridge, magnitude_sys_pu, rng, t_now, cfg) -> DisturbanceTrace`.
  RNG is **explicitly injected per call** (no module-level
  `np.random` calls in the adapter file).
- Four frozen-dataclass adapters, one per workspace-var family:
  - `EssPmStepProxy(target_indices, proxy_bus)` — covers
    `pm_step_proxy_bus7`, `pm_step_proxy_bus9`,
    `pm_step_proxy_random_bus`, `pm_step_single_vsg`.
  - `SgPmgStepProxy(target_g)` — covers `pm_step_proxy_g1/g2/g3` +
    `pm_step_proxy_random_gen`.
  - `LoadStepRBranch(ls_bus)` — covers `loadstep_paper_bus14/bus15` +
    `loadstep_paper_random_bus`. Writes use `require_effective=True`
    (raises under v3 due to R-block compile-freeze).
  - `LoadStepCcsInjection(ls_bus)` — covers
    `loadstep_paper_trip_bus14/bus15` +
    `loadstep_paper_trip_random_bus`. Same `require_effective=True`.
- `resolve_disturbance(disturbance_type, vsg_indices=None)` factory
  for the 14 type strings + `pm_step_single_vsg`.

Sentinel strings `"random_bus"` / `"random_gen"` distinguish random
selection from explicit-target tuples (an explicit `(0, 3)` is
"spread", not "random pick"). Resolved via injected `rng` inside
`apply()`.

### C4 — Scenario value object

`KundurSimulinkEnv.reset` signature extended:
```python
reset(self, seed=None, options=None, *, scenario=None)
```

Three input modes (priority order):

1. `scenario: Scenario` — typed VO. Translated to a concrete
   `disturbance_type` via existing `scenario_to_disturbance_type()`;
   magnitude from `scenario.magnitude_sys_pu`. Internal trigger
   armed.
2. `options['disturbance_magnitude']` — magnitude only.
   `_disturbance_type` stays at constructor / `KUNDUR_DISTURBANCE_TYPE`
   default. Internal trigger armed. Used by train-loop random path
   and paper_eval LoadStep path.
3. Neither — internal trigger DISARMED. Legacy probe path drives
   dispatch via `apply_disturbance(...)` directly.

`options['trigger_at_step']` (int, default `int(0.5/DT) = 2`) controls
when the internal trigger fires. paper_eval uses `0` for immediate
post-warmup dispatch (matches legacy timing).

`apply_disturbance(...)` retained as public API; emits
`DeprecationWarning` and sets `_disturbance_triggered = True` to
prevent double-fire when callers mix legacy + new patterns.

### Constraint: Scenario is NOT a complete execution protocol (§1.5b)

Same `Scenario` may resolve to different `disturbance_type` strings
under different env-construction context (env-var, options
short-circuit, future translator changes). Therefore the **resolved**
`disturbance_type` MUST be recorded per-episode for audit and
reproducibility:

- `env._episode_resolved_disturbance_type` set at `reset()`
- Exposed in `step()` info dict as `info["resolved_disturbance_type"]`
  + `info["episode_magnitude_sys_pu"]`
- `train_simulink.py` persists into `physics_summary[ep]` entry
- `paper_eval.py` retains its existing per-episode metrics row
  (proxy_bus + magnitude_sys_pu fields are sufficient context)

The translator may evolve; the recorded field is the single source of
truth for what was actually written to MATLAB.

### `_disturbance_type` policy

Stays as a regular instance attribute (not @property). Train and
paper_eval no longer write it (M3, M4 of the spec). Probes (6 callers)
keep the legacy `env._disturbance_type = ...; env.apply_disturbance(...)`
pattern; backward-compat preserved via the field's regular-attr nature.

## Consequences

### Positive

- The 14 disturbance-type strings collapse into 4 testable adapter
  classes. Adding a new type requires editing one place
  (`_DISPATCH_TABLE`) plus a new adapter file (or a new sentinel on
  an existing adapter).
- `_apply_disturbance_backend` body shrinks from 235 lines (CVS branch)
  to 16 lines. Soft target ≤30 hit; hard cap ≤45 met (40 lines total
  including 20-line SPS legacy fall-through).
- Per-episode disturbance has one entry point (`env.reset(scenario=...)`)
  for the paper-replication path; step-loop `apply_disturbance` calls
  removed from train.
- §1.5b audit trail concentrates "what was actually written" in one
  place per episode. Run replay reads `resolved_disturbance_type` from
  the log instead of re-deriving from Scenario fields.
- Adapters are independently testable with a fake bridge that records
  writes. Test surface: 145 tests (60 schema + 71 protocol +
  14 env API).

### Negative

- The translator `scenario_to_disturbance_type()` is now load-bearing
  (Scenario VO depends on it). Schema evolution requires updating both
  the translator and the recorded `resolved_disturbance_type` audit
  semantics.
- Sentinel strings (`"random_bus"`, `"random_gen"`) are weakly typed.
  A typo in a custom factory call would produce a `ValueError` at
  apply time, not at construction. (Acceptable trade-off: `_DISPATCH_TABLE`
  is the canonical entry; ad-hoc construction is rare.)
- Two RNG sources still active in `train_simulink.py`: the env's
  `np_random` (used by `EssPmStepProxy("random_bus")` etc. inside
  `apply()`) and the module-level `np.random` (used by
  `_episode_reset_kwargs` to draw magnitudes for the no-scenario_set
  random path). Unifying these is C4-adjacent but deferred.

### Forward implications

- **C2 (BridgeConfig discriminated union) — deferred** but with an
  explicit trigger contract:
  - Trigger 1: production code grows an 8th `if cfg.model_name in (...)`
    or `if profile.model_name == 'kundur_*'` branch (current count = 7)
  - Trigger 2: a 3rd Kundur profile is added (e.g. `kundur_cvs_v4`,
    `kundur_phasor_*`), breaking the v2/v3 binary
  - Trigger 3: NE39 scenario adopts a similar dual-step_strategy
    pattern
  - **No calendar safety net** (per spec §4.4).
  - PRs that satisfy a trigger must mention "triggers C2 reopen" in
    the description so future maintainers don't miss the signal.

- **`KUNDUR_DISTURBANCE_TYPE` default mismatch** (surfaced by P4
  smoke): default is `loadstep_paper_random_bus` per Credibility Close
  lock; C3d (require_effective=True) makes that default raise on every
  call. Production workflow currently relies on env-var override. Fix
  (align default with paper_eval's de-facto `pm_step_proxy_random_bus`)
  is out of C4 scope; tracked separately.

- **Bridge.warmup `kundur_cvs_ip` struct writes** still bare-string
  (not in workspace_vars schema). Out of C1/C4/C2 scope; would need
  a `STRUCT` family extension to the schema.

## References

- Spec: `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`
- Plans: `docs/superpowers/plans/2026-04-29-kundur-cvs-algo-refactor.md`
  (parent), `2026-04-29-c1-disturbance-protocol-design.md` (C1 design),
  `2026-04-29-c4-scenario-vo-design.md` (C4 design)
- Verdicts: `quality_reports/verdicts/2026-04-29_p0_c3_closure.md`,
  `2026-04-29_p2_c1_disturbance_protocol_implementation.md`,
  `2026-04-29_p4_c4_implementation.md`,
  `2026-04-29_p4_smoke_results.md`
- ADRs: `2026-04-10-paper-baseline-contract.md` (locked constants),
  `2026-04-29-kundur-workspace-var-schema-boundary.md` (C3 schema
  boundary)
- Commits: `0af9813` (P0 / C3 closure), `e55a623` (P1), `44a34a8`
  (P2 / C1 implementation), `e840f96` (P3), `c89c59d` (P3 patch),
  `1e8af12` (P4a / C4 env API), `0d80be7` (P4b / call site migration)
