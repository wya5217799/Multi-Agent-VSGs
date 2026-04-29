# P4 Verdict — C4 Scenario VO Implementation

**Stage:** P4 of `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`
**Date:** 2026-04-29
**Result:** PASS (Y4 real-MATLAB smoke deferred to user authorization)
**Predecessors:** P3 commit `c89c59d`, P4a commit `1e8af12`
**Next:** P5 (documentation finalization + Y1 oracle cleanup)

---

## 1. Tests

```
pytest tests/test_kundur_env_scenario_api.py
       tests/test_disturbance_protocols.py
       tests/test_kundur_workspace_vars.py -q
=> 145 passed in 0.36s
```

Breakdown unchanged from P4a baseline (60 + 71 + 14).

## 2. Spec compliance — M3/M4/M5 grep verification

### M3: train_simulink — no `env._disturbance_type =` writes
```
grep -nE "env\._disturbance_type\s*=" scenarios/kundur/train_simulink.py
=> 1 hit on line 489 — INSIDE A DOCSTRING (literal text describing
   deleted legacy code; not an actual assignment)
=> 0 code assignments
```
PASS.

### M4: paper_eval — no `env._disturbance_type =` writes
```
grep -nE "env\._disturbance_type\s*=" evaluation/paper_eval.py
=> 0 hits
```
PASS.

### M5: `_ep_disturbance` closure deleted
```
grep -n "def _ep_disturbance" scenarios/kundur/train_simulink.py
=> 0 hits
```
Replaced by `_episode_reset_kwargs(ep_idx)` returning a kwargs dict
for `env.reset()`. PASS.

## 3. Migration summary

### 3.1 train_simulink.py

| Change | Lines | Status |
|---|---|---|
| `_ep_disturbance` closure | DELETED (was 474-486) | ✅ |
| Replaced with `_episode_reset_kwargs(ep_idx)` | NEW | ✅ |
| Bootstrap reset (was 491-494: `_disturbance_type=` + `options=`) | `env.reset(**_episode_reset_kwargs(start_episode))` | ✅ |
| Per-episode reset (was 597-600) | `env.reset(**_episode_reset_kwargs(ep))` | ✅ |
| Step-loop apply_disturbance (was 619-621) | DELETED — env.step internal trigger fires | ✅ |
| `evaluate()` apply_disturbance (line 276) | KEPT — research-artifact, DeprecationWarning suppressed via `warnings.catch_warnings()` | ✅ (M3 satisfied; not a `_disturbance_type=` write) |
| `physics_summary[ep]` log entry | Added `resolved_disturbance_type` + `episode_magnitude_sys_pu` from `last_info` | ✅ §1.5b |

### 3.2 paper_eval.py

| Change | Lines | Status |
|---|---|---|
| 5 `env._disturbance_type =` writes (was 246-254) | DELETED, replaced with Scenario VO construction | ✅ |
| `apply_disturbance(magnitude=mag)` (was 260) | DELETED — replaced by `env.reset(scenario=..., options={'trigger_at_step': 0})` | ✅ |
| LoadStep path (preferred_type starts with `loadstep_paper_`) | `env.reset(seed, options={'disturbance_magnitude': mag, 'trigger_at_step': 0})` — magnitude path with trigger_at_step=0 | ✅ |
| Pm-step path (default) | Build typed `Scenario(scenario_idx, kind, target, magnitude_sys_pu)` from bus → kind/target translation; pass via `env.reset(scenario=...)` | ✅ |

## 4. Risk coverage (R-1 to R-6 from P3 §5)

| ID | Status |
|---|---|
| R-1 trigger time off-by-one | Unit-tested in `TestR1_TriggerTime` (P4a, 5 cases) |
| R-2 mixed-API double-fire | Unit-tested in `TestR2_NoDoubleFire` (P4a, 2 cases) |
| R-3 RNG order drift in train random | Code-level: `np.random.uniform` retained in `_episode_reset_kwargs`; same draw order as legacy `_ep_disturbance` |
| R-4 `_disturbance_type` external write breaks | Unit-tested in `TestR4_DisturbanceTypeAttrCompat` (P4a, 3 cases) |
| R-5 paper_eval byte-level diverges | Code-level: `trigger_at_step=0` matches legacy timing; magnitude / type translation deterministic |
| R-6 DeprecationWarning floods stderr | paper_eval migrated entirely (no apply_disturbance call); train evaluate() suppresses via `warnings.simplefilter` |

## 5. M9 / M10 real-MATLAB smoke — DEFERRED to user authorization

Per spec §3.1:
- M9: P4 5-ep cold smoke ×2 with ±1% tolerance
- M10: paper_eval 1-ep smoke byte-level on deterministic oracle

These require MATLAB engine and were marked as Y4 (optional, by user
decision). Recommendation: user runs:

```bash
# Mode 1: random disturbance baseline
python -m scenarios.kundur.train_simulink --episodes 5 --mode simulink --seed 42

# Mode 2: scenario_set test
python -m scenarios.kundur.train_simulink --episodes 5 --scenario-set test --seed 42

# paper_eval 1-ep (KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus)
python -m evaluation.paper_eval --n_scenarios 1 --bus_choices 2
```

Compare INCLUDED fields (§4.6 deterministic oracle) with the most
recent baseline run; any divergence > ±1% on `mean_reward` /
`max_freq_dev_hz` is a regression.

## 6. Files changed (P4 = 4a + 4b)

### P4a (commit 1e8af12)
- `env/simulink/kundur_simulink_env.py` (+115 lines)
- `tests/test_kundur_env_scenario_api.py` (NEW, 260 lines)

### P4b (this commit)
- `scenarios/kundur/train_simulink.py` (~30 lines edited)
- `evaluation/paper_eval.py` (~50 lines edited)

## 7. What this verdict does NOT establish

- Real MATLAB byte-level regression (M9/M10) — pending user authorization
- The training-loop reward landscape after C4 — pending real-MATLAB smoke
- Probe migration — out of scope (R-4 backward compat preserved)

## 8. Entry conditions for P5

- [x] M3/M4/M5 grep clean
- [x] All unit tests PASS (145/145)
- [x] R-1, R-2, R-4 unit-test covered
- [x] R-3, R-5, R-6 code-level mitigations applied
- [ ] User authorization for P5
- [ ] (Optional) M9/M10 real-MATLAB smoke executed and PASS

## 9. P5 scope (next stage)

- Update `scenarios/kundur/NOTES.md` with C1+C4 known facts
- Update `CLAUDE.md` 常见修改点定位 with disturbance_protocols and
  Scenario VO entries
- New ADR `docs/decisions/2026-04-29-kundur-cvs-disturbance-protocol-and-scenario-vo.md`
  with C1+C4 contracts and C2 deferred trigger conditions
- (Y1) Delete `tests/_disturbance_backend_legacy.py` after declaring
  C4 stable
- 1 commit, ~30 min
