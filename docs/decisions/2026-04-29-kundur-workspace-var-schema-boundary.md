# Kundur Workspace Var Schema Boundary

## Status
Accepted (2026-04-29)

## Context

The Kundur CVS environment writes ~25 MATLAB base-workspace variables per
episode (M/D per ESS, Pm/Pmg-step, LoadStep, LoadStep-Trip). Before C3 every
write site used a raw string literal:

```python
self.bridge.apply_workspace_var(f'Pm_step_amp_{i+1}', amp)
self.bridge.apply_workspace_var('LoadStep_amp_bus14', 0.0)
```

Three failure modes accumulated:

1. **Silent typos**: `LoadStep_amp_Bus14` (capitalised B) writes a dangling
   base-workspace entry; the Constant block keeps reading the old value.
2. **Profile drift**: variables that exist on the v3 MATLAB side (e.g.
   `PmgStep_amp_g`) but not on v2 are written under v2 with no error.
3. **Compile-frozen consumers**: writing `LoadStep_amp_bus14` under v3
   succeeds at the workspace level but the Series RLC R-block has its
   Resistance string compile-frozen at FastRestart — the disturbance does
   not actually fire. (Documented in `scenarios/kundur/NOTES.md`
   §"2026-04-29 Eval 协议偏差".)

C3 introduces `scenarios/kundur/workspace_vars.py` with a typed schema
(`resolve(key, profile, **idx)`) that all env-side write sites now go
through.

## Decision

### Scope (what the schema covers)

- All `apply_workspace_var` write sites in `KundurSimulinkEnv`:
  - `_reset_backend` (v3 IC restoration)
  - `_apply_disturbance_backend` (Pm-step / Pmg-step / LoadStep dispatch)
- The schema is the **single Python-side document** of the Python ↔ MATLAB
  contract for these variables.
- Schema entries are profile-aware: `profiles=frozenset(...)` declares
  which `KundurModelProfile.model_name` values may write each variable.

### Out of scope (what the schema does NOT cover)

- `SimulinkBridge.warmup` / `_warmup_cvs` (writes `kundur_cvs_ip` struct
  via a separate path).
- `BridgeConfig` template fields (`m_var_template`, `omega_signal`, etc.)
  — string templates remain in config layer.
- NE39 / legacy SPS `M0_val_ESi` / `D0_val_ESi` family (separate scenario).
- MATLAB-side consumer registration (no auto-detection that
  `LoadStep_amp_bus14` actually drives a live block).

### Two-tier validation: name-valid vs physically-effective

A variable name being **name-valid** in a profile (`profile in
spec.profiles`) means the MATLAB Constant block references that workspace
name — `apply_workspace_var` will not produce a dangling base-ws entry,
and typos are caught.

A variable name being **physically effective** in a profile (`profile in
spec.effective_in_profile`) is a strictly stronger claim: writes to that
name produce a paper-grade physical disturbance under the profile's
solver / FastRestart contract.

The two are deliberately separate to handle the v3 LoadStep case:
`LoadStep_amp_bus14` is name-valid in v3 (the Constant block reads it)
but not physically effective (the downstream R-block Resistance is
compile-frozen).

`resolve(...)` enforces only name-validity by default. Pass
`require_effective=True` to additionally reject name-valid but
not-effective combinations. Disturbance-dispatch sites use
`require_effective=True`; IC seeding sites (which legitimately want to
write the name even when no transient is expected) use the default.

### Hard rule: `effective_in_profile` is advanced only by physics fix

The `effective_in_profile` set is a hand-curated snapshot of post-physics
state. There is no auto-detection. When the physics layer is repaired
(e.g. R-block edited so the Resistance is re-evaluated under
FastRestart), the matching schema entry must be hand-promoted in
`workspace_vars.py`. Code-level refactors (including future C1, C4, C2
work) **must not** modify `effective_in_profile`.

This rule prevents the failure mode where a refactor "tidies up" the
schema by removing an `effective_in_profile=frozenset()` exclusion
without actually fixing the underlying physical channel.

## Consequences

### Positive

- Renaming a workspace variable is a one-line edit in `workspace_vars.py`;
  the previous failure mode (rename in `build_kundur_cvs_v3.m` →
  silent dead writes from env) is eliminated.
- The schema is auditable: `keys()` and `spec_for(key)` introspection
  let tests and probes verify what variables are declared.
- The two-tier validation makes the v3 LoadStep dead-channel state
  explicit at the call site (via `require_effective=True`) rather than
  buried in a comment about R-block compile-freeze.
- Name-valid-but-not-effective entries carry a machine-readable
  `inactive_reason` dict that is surfaced in `WorkspaceVarError`
  messages.

### Negative

- The schema duplicates information that exists on the MATLAB side
  (`build_kundur_cvs_v3.m` declares the same variable names). Drift
  between the two is possible; mitigation is the existing
  `tests/test_kundur_workspace_vars.py::TestFixtureCrossCheck` which
  verifies a small subset of variables match the fixture file derived
  from the MATLAB build.
- Adding a new variable requires editing `workspace_vars.py` in addition
  to the env call site. This is intentional (the schema is the contract),
  but adds friction relative to the old free-string approach.
- The `effective_in_profile` set must be advanced manually after physics
  fixes. Physics engineers and Python authors must coordinate.

### Forward implications (downstream candidates)

- C1 (DisturbanceProtocol seam, `2026-04-29-kundur-cvs-algo-refactor`
  spec): protocol adapters consume schema keys (`PM_STEP_AMP`,
  `LOAD_STEP_AMP`, etc.) instead of raw strings; `require_effective=True`
  is wired at the protocol level for LoadStep family.
- C2 (BridgeConfig discriminated union): when this is eventually done,
  the schema's `profiles` field becomes the source of truth; the
  `model_name in (...)` runtime branches in env collapse.
- Bridge.warmup migration (out of scope here): if `kundur_cvs_ip` struct
  writes are ever migrated to schema, the schema must grow a
  `STRUCT` family or equivalent.

## References

- `scenarios/kundur/workspace_vars.py` — the schema
- `tests/test_kundur_workspace_vars.py` — 60 tests covering schema
  invariants, name-validity, effectiveness, env wiring
- `scenarios/kundur/NOTES.md` §"2026-04-29 Eval 协议偏差" — physics-level
  context for v3 LoadStep dead channel
- `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md` —
  parent spec for algorithm-layer refactor (C1 + C4)
- Commits: `dcd87f6` (initial schema), `fa44cba` (name-valid vs
  effective split), `aad5359` (require_effective wired at LoadStep
  dispatch)
