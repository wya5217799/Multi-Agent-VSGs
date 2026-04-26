# Kundur CVS v3 — Phase 3 RL-Readiness Entry Plan (DRAFT)

> **Status:** DRAFT (planning only — no env / profile / bridge / SAC / training edits)
> **Date:** 2026-04-26
> **Predecessor:** `2026-04-26_kundur_cvs_v3_plan.md` (master plan)
> **Phase 1 commit:** `a40adc5` (NR + build)
> **Phase 2 commits:** `7911e28` (fix-A2 build alignment) → `c1c8323` (probes + verdicts) → `805c6b6` (P2.5c) → `a27b0be` (aggregate addendum)
> **Phase 2 status:** CONDITIONAL PASS / GO TO NEXT DESIGN DECISION (confirmed)

---

## 1. What Phase 3 IS and IS NOT

### Phase 3 IS
- Wiring v3 model into the existing RL training plumbing (env, bridge, profile dispatch)
- Verifying a 5-episode round-trip end-to-end smoke
- Establishing the v3 RL contract on top of the validated Phase 2 physics
- A documented hand-off from "the model works" to "the agent can train against it"

### Phase 3 is NOT
- Phase 4 (the 50-ep PHI gate / reward-shaping experiment)
- Phase 5 (long training + paper baseline comparison)
- A second pass at physics validation
- An opportunity to retune dispatch / V_spec / line / IC / NR

---

## 2. Hard boundaries (locked)

Phase 3 may **only** edit / create:

```
ALLOW
  scenarios/kundur/model_profiles/kundur_cvs_v3.json     (NEW; mirrors v2 profile schema)
  scenarios/kundur/config_simulink.py                    (extend dispatch ladder for v3)
  env/simulink/kundur_simulink_env.py                    (extend apply_disturbance with type routing)
  probes/kundur/v3_dryrun/probe_5ep_smoke.py             (NEW; round-trip integration probe)
  results/harness/kundur/cvs_v3_phase3/                  (NEW dir; verdicts + summary)
  quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md  (this file, edits as plan evolves)
```

Phase 3 may **NOT** edit:

```
DENY
  scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m   (locked by Phase 1)
  scenarios/kundur/kundur_ic_cvs_v3.json                              (locked by Phase 1)
  scenarios/kundur/simulink_models/build_kundur_cvs_v3.m              (locked by fix-A2)
  scenarios/kundur/simulink_models/kundur_cvs_v3.slx                  (locked by fix-A2)
  scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat          (locked by fix-A2)

  scenarios/kundur/kundur_ic.json                                     (v2; untouched forever in v3)
  scenarios/kundur/kundur_ic_cvs.json                                 (v2; untouched forever in v3)
  scenarios/kundur/simulink_models/build_kundur_cvs.m                 (v2; untouched forever in v3)
  scenarios/kundur/simulink_models/kundur_cvs.slx                     (v2; untouched forever in v3)
  scenarios/kundur/simulink_models/kundur_cvs_runtime.mat             (v2; untouched forever in v3)
  scenarios/kundur/model_profiles/kundur_cvs.json                     (v2; untouched forever in v3)

  scenarios/new_england/                                              (NE39; untouched forever in v3)
  agents/                                                             (SAC; untouched in Phase 3)
  engine/simulink_bridge.py                                           (`cvs_signal` already exists)
  engine/run_schema.py / run_protocol.py                              (training schema; untouched)
  utils/monitor.py / training_*.py                                    (training plumbing; untouched)
  scenarios/contract.py                                               (KUNDUR contract; untouched)
  scenarios/config_simulink_base.py                                   (SAC base hyper; untouched)
```

Any deviation from the allow-list = STOP and request user authorization.

---

## 3. Phase 3 deliverables (4 sub-steps, halt after each)

### P3.1 — `model_profiles/kundur_cvs_v3.json`

Mirror existing v2 profile shape ([`scenarios/kundur/model_profiles/kundur_cvs.json`](../../scenarios/kundur/model_profiles/kundur_cvs.json)):

```jsonc
{
  "scenario_id": "kundur",
  "profile_id": "kundur_cvs_v3",
  "model_name": "kundur_cvs_v3",
  "solver_family": "sps_phasor",
  "pe_measurement": "vi",
  "phase_command_mode": "passthrough",
  "warmup_mode": "technical_reset_only",
  "feature_flags": {
    "allow_pref_ramp": false,
    "allow_simscape_solver_config": false,
    "allow_feedback_only_pe_chain": false
  }
}
```

**Verify:** schema validation passes. `python -c "from scenarios.kundur.model_profile import load_kundur_model_profile; p = load_kundur_model_profile('scenarios/kundur/model_profiles/kundur_cvs_v3.json'); print(p)"` returns the parsed object.

**Halt for user GO.**

### P3.2 — `config_simulink.py` v3 dispatch branch

Extend the existing CVS branch (~line 120) with a third case for `kundur_cvs_v3`. Reads `kundur_ic_cvs_v3.json` (Phase 1 IC, schema_version=3), wires the v3-specific scalars:

```python
elif KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs_v3':
    import json as _json
    _v3_ic_path = Path(__file__).resolve().parent / 'kundur_ic_cvs_v3.json'
    with _v3_ic_path.open(encoding='utf-8') as _f:
        _v3_ic_raw = _json.load(_f)
    VSG_PE0_DEFAULT_SYS = np.asarray(_v3_ic_raw['vsg_pm0_pu'], dtype=np.float64)   # [-0.369, ...]
    VSG_DELTA0_RAD      = np.asarray(_v3_ic_raw['vsg_internal_emf_angle_rad'], dtype=np.float64)
```

`KUNDUR_BRIDGE_CONFIG` `m_var_template` / `d_var_template` / `omega_signal` remain `M_{idx}` / `D_{idx}` / `omega_ts_{idx}` for v3 (matches v2 CVS pattern; build emits `omega_ts_ES1..ES4` AND `omega_ts_G1..G3` — bridge only needs ESS).

But: build_kundur_cvs_v3.m emits loggers as `omega_ts_ES<N>` (suffix `ES`), not `omega_ts_<N>`. Bridge CVS dispatch uses `omega_ts_{idx}` template with `idx ∈ {1..4}` → would look for `omega_ts_1`. **MISMATCH** — bridge template needs to produce `omega_ts_ES{idx}` for v3. Check current bridge template handling; may need explicit override in v3 BridgeConfig.

**Sub-task P3.2a — bridge contract check**: read `engine/simulink_bridge.py` `cvs_signal` step strategy + `omega_signal` resolution. Decide whether v3 needs an `omega_signal` override in `BridgeConfig` or a build-side rename. **Build-side rename is FORBIDDEN by allow-list** — must be solved on bridge config side via existing `omega_signal` parameter.

**Halt for user GO** before any code edit.

### P3.3 — `env/simulink/kundur_simulink_env.py` apply_disturbance extension

Extend `_apply_disturbance_backend` for v3-specific disturbance types:

```python
def _apply_disturbance_backend(
    self,
    bus_idx: Optional[int],
    magnitude: float,
    disturbance_type: str = 'pm_step_single_vsg',  # default = current v2 behavior
) -> None:
    cfg = self.bridge.cfg
    if cfg.model_name == 'kundur_cvs_v3':
        if disturbance_type == 'pm_step_random_source':
            # extend to G1/G2/G3 + ES1..4 (7 sources)
            ...
        elif disturbance_type == 'load_step_random_bus':
            # set LoadStep7 or LoadStep9 R via set_param
            ...
        elif disturbance_type == 'wind_trip':
            # set WindAmp_1 or WindAmp_2 via assignin
            ...
        else:  # default 'pm_step_single_vsg' for v2 contract
            ...
    else:
        # untouched v2 / SPS / legacy code path
        ...
```

**v2 contract preserved** — default disturbance type matches current behavior, all v2 callers unaffected.

Pre-known caveats from Phase 2:
- Bus 9 LoadStep stiff (Bus 7 preferred for training disturbance variety)
- W2 wind trip via `WindAmp → 0` is artifact-prone (use partial trip ≤ 50 % only, or restrict to W1)

**Halt for user GO** before any code edit.

### P3.3b — Warmup feasibility decision (NEW gate, blocks P3.4)

User-mandated gate (added 2026-04-26): before any 5-ep smoke, write a
short feasibility doc that answers:

1. Phase 2 found inductor-IC kick takes ~30 s to fully decay (P2.5b decay-tau ~3-4 s × ~7 cycles).
2. Current Kundur `T_WARMUP = 3.0` (v2 override at config_simulink.py:46) and `T_EPISODE = 10 s`.
3. Can existing warmup mechanism absorb the v3 kick within an acceptable budget? Options to evaluate:
   - (a) raise `T_WARMUP` to 30 s, accepting ~30 s/ep wall overhead → 50-ep gate ~25 min wall
   - (b) inject NR-derived inductor IC into Series RLC L blocks at runtime (build edit, FORBIDDEN by allow-list — would defer to a separate authorized work item)
   - (c) accept residual transient inside episodes; rely on per-step Pe/omega readings being accurate after settle (sub-30 s residual is < 1 mHz/decade per P2.5 decay table, may be acceptable)

4. Verdict: which option is viable WITHOUT violating the Phase 3 allow-list, and what is the minimum-overhead choice?

Halt for user GO. **P3.4 cannot run until P3.3b returns a viable option.**

### P3.4 — 5-episode round-trip smoke (`probe_5ep_smoke.py`)

**BLOCKED by P3.3b warmup feasibility decision.**


Set env var `KUNDUR_MODEL_PROFILE=…/kundur_cvs_v3.json`, run 5 episodes via existing `train_simulink.py` infrastructure but with `--episodes 5 --no-checkpoint --no-eval` (or smoke-only flag — exact CLI TBD when reading current train script). 

Pass criteria:
- 5/5 episodes complete (no NaN / Inf / clip / Simscape constraint violation)
- per-ep df ∈ [0.1, 5] Hz (paper reach band)
- `events.jsonl` (or equivalent run log) shows correct disturbance type routing
- `training_status.json` schema valid
- v3 wall time < 30 s/ep (informational; v2 baseline ~9 s/ep, expect 2-3× v3 due to 16-bus)

**Halt with verdict** — do NOT auto-proceed to Phase 4.

---

## 4. Pre-Phase-3 dependency checks (read-only audit)

Before P3.1 is started, read the following files to confirm no surprises:

| File | What to check | Why |
|---|---|---|
| `scenarios/kundur/model_profile.py` | `load_kundur_model_profile()` schema validator | confirm v3 profile JSON shape will be accepted as-is |
| `scenarios/kundur/config_simulink.py:L120-130` | current `if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs'` branch | identify the exact `elif` insertion point |
| `engine/simulink_bridge.py` `cvs_signal` step strategy | how `omega_signal` template is resolved (raw string vs `.format(idx=...)`) | decide whether v3 needs `omega_signal='omega_ts_ES{idx}'` override |
| `env/simulink/kundur_simulink_env.py:678-745` | current `_apply_disturbance_backend` for `kundur_cvs` | identify non-conflicting extension surface |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | which signals it reads from base ws / ToWorkspace | confirm v3 ESS logger names match |

**Read-only audit ≠ edit.** Output the audit findings into a Phase 3 read-out doc, then halt for user GO before any code change.

---

## 5. Risks (Phase 3-specific)

| ID | Risk | Mitigation |
|---|---|---|
| R-P3-1 | Build-side ESS logger names (`omega_ts_ES1..ES4`) don't match bridge `omega_signal='omega_ts_{idx}'` (which would try `omega_ts_1`) | Solve via `omega_signal='omega_ts_ES{idx}'` in v3 `BridgeConfig` (existing parameter, no build edit) |
| R-P3-2 | Build-side SG loggers (`omega_ts_G1..G3`) are present but bridge only consumes ESS-indexed loggers (n_agents=4). SG / wind data is logged but not consumed | OK — SG / wind loggers are diagnostic only; bridge ignores them |
| R-P3-3 | LoadStep / WindAmp mid-sim toggle requires `set_param` / `assignin` from Python via MATLAB engine | env apply_disturbance path already uses `bridge.apply_disturbance_load`; extend with `bridge.assign_workspace` (if not present, may need a thin helper — check during P3.2a audit) |
| R-P3-4 | v3 wall time per episode > 30 s would slow Phase 4 50-ep gate to > 25 min | Acceptable for Phase 4; if > 60 s/ep, defer to Phase 4 perf optimisation work, not block Phase 3 |
| R-P3-5 | Inductor-IC kick (~30 s per Phase 2 finding) consumes > 30 % of episode time if T_EPISODE = 10 s | T_WARMUP set to absorb the kick; current v2 base T_WARMUP = 0.5 s, Kundur override = 3 s. v3 may need T_WARMUP = 30 s OR re-design the warmup pattern (Phase 3.5 deferred decision) |
| R-P3-6 | RL agent learns to exploit Bus 7 / Bus 9 asymmetry (Bus 9 stiff per P2.3-L1) → biased policy | Document; Phase 4 should sample disturbance bus uniformly to expose the agent to both regimes |
| R-P3-7 | Reward shaping defaults `PHI_H = PHI_D = 1e-4` (B1 baseline) ignore the H/D asymmetry surfaced by P2.5c | Phase 4 reward-shaping experiment (the dual-PHI sweep already in master plan §4.4) is the right place to address; Phase 3 keeps current defaults |

---

## 6. Phase 3 → Phase 4 hand-off contract

Phase 3 done = v3 5-ep smoke green AND profile + dispatch + env all in shape that Phase 4 50-ep gate can be invoked by:

```
KUNDUR_MODEL_PROFILE=scenarios/kundur/model_profiles/kundur_cvs_v3.json \
  python -m scenarios.kundur.train_simulink --episodes 50 \
    --output results/sim_kundur/runs/kundur_cvs_v3_50ep_baseline
```

(Exact CLI shape TBD — read `scenarios/kundur/train_simulink.py` current options before drafting Phase 4.)

---

## 7. What this plan does NOT decide

- **P3.5 / warmup design** (separate decision after P3.4 smoke reveals episode wall time)
- **PHI_H / PHI_D values for v3** (Phase 4 reward-shaping experiment)
- **disturbance probability mix across pm_step_random_source / load_step_random_bus / wind_trip** (Phase 4 dataset design)
- **Phase 5 baseline implementations** (adaptive inertia, centralized SAC — separate plans)

These are intentionally deferred to keep Phase 3 small.

---

## 8. Sub-step cadence (mirrors Phase 2)

```
P3.0 read-only dependency audit  →  halt, present findings, request GO
  ↓
P3.1 model_profiles JSON         →  halt, request GO
  ↓
P3.2 config_simulink.py dispatch →  halt, request GO
  ↓
P3.3 env apply_disturbance ext   →  halt, request GO
  ↓
P3.3b warmup feasibility doc     →  halt with viable-option verdict, request GO
  ↓
P3.4 5-ep smoke probe            →  halt with verdict, request GO for Phase 4
```

Each sub-step has its own micro-verdict + commit. No batch commits across sub-steps.

---

## 9. Decision points for user

1. Approve this Phase 3 plan as written?
2. Ready to start P3.0 (read-only dependency audit) immediately, or stage it for a later session?
3. Any adjustments to the allow-list / deny-list?

**No code or model changes happen until user approves.**
