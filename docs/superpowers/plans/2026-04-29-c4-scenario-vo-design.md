# P3 — C4 Scenario VO Design (no-code)

**Stage:** P3 of `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`
**Date:** 2026-04-29
**Status:** DRAFT — awaiting user review before P4 entry
**Predecessor:** P2 commit `44a34a8`
**No code changes in this stage.** Design only.

---

## 0. Goal

Collapse 4 disturbance entry points into a single typed input `Scenario`,
move trigger time `step == int(0.5/DT)` into env, eliminate
`env._disturbance_type =` private mutation from train/eval call sites
(M3, M4, M5).

Scope: env API + 2 call sites (`scenarios/kundur/train_simulink.py`,
`evaluation/paper_eval.py`). Probes / scripts / tests keep using
`apply_disturbance(...)` legacy API with `DeprecationWarning`.

---

## 1. New env API

### 1.1 Signature

```python
def reset(
    self,
    *,
    seed: Optional[int] = None,
    scenario: Optional[Scenario] = None,
    options: Optional[dict] = None,
) -> Tuple[np.ndarray, dict]:
    """Reset environment.

    Disturbance source (priority order):
      1. ``scenario`` — typed value object carrying (kind, target,
         magnitude_sys_pu). Internal trigger arms for step==trigger_at_step.
      2. ``options['disturbance_magnitude']`` — magnitude only;
         disturbance_type derived from constructor / KUNDUR_DISTURBANCE_TYPE
         env-var. Internal trigger arms identically.
      3. None / no scenario / no magnitude — internal trigger DISARMED;
         legacy ``apply_disturbance(...)`` call drives dispatch (probes).

    ``options`` may also carry:
      - ``trigger_at_step``: int, 0-indexed; default ``int(0.5/DT)``
        (= 2 for DT=0.2s). paper_eval uses 0 to fire at episode start.
    """
```

### 1.2 Internal state added/changed

```python
# New per-episode state
self._episode_scenario: Scenario | None = None
self._episode_magnitude: float | None = None        # resolved at reset
self._trigger_at_step: int = int(0.5 / DT)          # default = 2
self._disturbance_triggered: bool = True            # True = no internal trigger
```

`_disturbance_type` STAYS as a regular instance attr (not @property).
Scenario API writes to it internally; external writes (probes) still
work as before. M3/M4 are satisfied because train/paper_eval **stop
writing it**, not because the field disappears.

### 1.3 Trigger logic inside `step()`

```python
def step(self, action):
    # ... action clip / decode (unchanged) ...

    # Internal disturbance trigger (C4) — fires once per episode at the
    # step boundary set by reset(). Matches legacy train-loop timing
    # (apply_disturbance called BEFORE bridge.step at step == int(0.5/DT)).
    if (not self._disturbance_triggered
            and self._step_count == self._trigger_at_step):
        self._apply_disturbance_backend(
            bus_idx=None, magnitude=float(self._episode_magnitude),
        )
        self._disturbance_triggered = True

    # ... existing _step_backend, _read_measurements, etc. ...
```

### 1.4 `apply_disturbance(...)` deprecation

```python
def apply_disturbance(self, bus_idx=None, magnitude=None):
    """Legacy disturbance entry point.

    Deprecated: prefer ``env.reset(scenario=Scenario(...))`` or
    ``env.reset(options={'disturbance_magnitude': mag})``. External
    callers (probes / scripts / tests) continue to work; calls bypass
    the internal step==trigger_at_step trigger and dispatch immediately.
    """
    warnings.warn(
        "env.apply_disturbance() is deprecated; pass a Scenario via "
        "env.reset(scenario=...) or magnitude via env.reset(options=...). "
        "External calls bypass the internal step trigger and dispatch "
        "immediately to the disturbance protocol layer.",
        DeprecationWarning, stacklevel=2,
    )
    if magnitude is None:
        magnitude = float(self.np_random.uniform(DIST_MIN, DIST_MAX))
        if self.np_random.random() > 0.5:
            magnitude = -magnitude
    self._apply_disturbance_backend(bus_idx, magnitude)
    # Mark triggered so internal trigger doesn't double-fire if a
    # caller mixes new + legacy patterns in the same episode.
    self._disturbance_triggered = True
```

### 1.5 `_disturbance_type` policy

| Caller pattern | Allowed? | Notes |
|---|---|---|
| `env.reset(scenario=Scenario(kind='gen', target=2, ...))` | ✅ preferred | Internally translates to `_disturbance_type = "pm_step_proxy_g2"` |
| `env.reset(options={'disturbance_magnitude': mag})` | ✅ preferred (random/LoadStep paths) | `_disturbance_type` left at constructor default |
| `env._disturbance_type = "pm_step_proxy_bus7"` | ⚠️ allowed for backward compat | Probes / legacy code; combined with `apply_disturbance()` for full legacy flow. Triggers no warning (silent backward-compat). M3/M4 require train/paper_eval NOT to use this pattern. |
| `env.apply_disturbance(magnitude=mag)` (after reset) | ⚠️ deprecated | DeprecationWarning. Bypasses internal trigger; works identically to legacy. |

---

## 2. Scenario VO field reuse

**Decision: reuse `scenarios.kundur.scenario_loader.Scenario` unchanged.**

Justification:
- Scenario fields (`scenario_idx`, `disturbance_kind`, `target`, `magnitude_sys_pu`, `comm_failed_links`) cover all `pm_step_proxy_*` types via the existing `scenario_to_disturbance_type()` translator (`scenario_loader.py:218-228`).
- LoadStep types (`loadstep_paper_*`, `loadstep_paper_trip_*`) — 6 types — are NOT translatable from kind/target. These types use the **`options['disturbance_magnitude']` path** with `_disturbance_type` from constructor / env-var. paper_eval already does this on the LoadStep branch (line 240-243).
- `pm_step_single_vsg` is also NOT translated by `scenario_to_disturbance_type`. Used only by probes, which keep the legacy `_disturbance_type=` write + `apply_disturbance` pattern. No migration needed.

So **`Scenario` covers Pm-step proxy paper-replication path**; LoadStep + single_vsg use options path; legacy probe pattern stays.

No new dataclass, no new fields. Locality: scenario_loader is the single place that defines Scenario.

---

## 3. Trigger-time policy

```python
# Default: train-loop semantics (apply at step 2, post-warmup wait of 0.4s)
self._trigger_at_step = int(0.5 / DT)  # = 2 for DT=0.2s

# paper_eval needs trigger at step 0 (immediate post-reset):
env.reset(scenario=scenario, options={'trigger_at_step': 0})
```

Why support both:
- Train: 0.4s post-reset wait for episode warmup expiry, then disturbance — matches legacy train timing exactly.
- paper_eval: t=0 trigger (apply_disturbance was called BEFORE step loop in legacy code) — matches legacy paper_eval timing exactly.

`trigger_at_step` lives in `options` dict (not a top-level kwarg) to keep the env API surface small. Documented in `reset()` docstring.

---

## 4. Migration table

### 4.1 train_simulink.py

| Line(s) | Old code | New code |
|---|---|---|
| 474-486 (`_ep_disturbance` closure) | Returns `(mag, type_override)` | **DELETED**. Inline construction below. |
| 491-494 (initial reset) | `env._disturbance_type = ...; env.reset(options={'disturbance_magnitude': dist_mag})` | `obs, _ = env.reset(scenario=scenario)` OR `env.reset(options={'disturbance_magnitude': dist_mag})` (random path) |
| 597-600 (per-episode reset) | `env._disturbance_type = _dtype_override; env.reset(options=...)` | Same as above |
| 619-621 (mid-step apply) | `if step == int(0.5/env.DT): env.apply_disturbance(magnitude=dist_mag)` | **DELETED** — env.step internal trigger handles this |
| 276 (`evaluate()` function) | `env.apply_disturbance(bus_idx=0, magnitude=_EVAL_DISTURBANCE_MAGNITUDE)` | `env.reset(scenario=Scenario(scenario_idx=0, disturbance_kind='bus', target=7, magnitude_sys_pu=_EVAL_DISTURBANCE_MAGNITUDE))` (or keep legacy with deprecation warning suppressed) |

**Result**: M3 (no `_disturbance_type =`), M5 (no `_ep_disturbance` closure), and the step loop has no `apply_disturbance` call.

### 4.2 evaluation/paper_eval.py

| Line(s) | Old code | New code |
|---|---|---|
| 240-256 (bus → type) | `env._disturbance_type = ...` per bus | Build `Scenario` per bus; LoadStep branch keeps env-var path with `options={'disturbance_magnitude': mag}` |
| 259-260 (reset + apply) | `env.reset(seed=...); env.apply_disturbance(magnitude=mag)` | `env.reset(seed=..., scenario=scenario, options={'trigger_at_step': 0})` |

**Result**: M4 (no `_disturbance_type =`).

### 4.3 Out of scope (legacy retained, no migration)

These keep `_disturbance_type =` writes / `apply_disturbance` calls — backward compat:

| File | Pattern | Why retained |
|---|---|---|
| `probes/kundur/v3_dryrun/_phi_root_cause.py:131,134` | Legacy write + apply | Diagnostic probe, set+fire pattern |
| `probes/kundur/v3_dryrun/_phi_resweep.py:135,276-279` | apply (default mag) + assert | Diagnostic probe |
| `probes/kundur/diagnose_*.py` (3 files) | apply call | Diagnostic |
| `probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py:71` | apply | Diagnostic |
| `scripts/profile_one_episode.py:35` | apply | Profiling utility |
| `scenarios/kundur/evaluate_simulink.py:145` | apply | Legacy non-paper evaluator |
| `tests/test_perf_episode_length.py:107,139` | apply | Performance tests |
| `tests/test_fixes.py:371,377` | monkey-patch | Mock test |
| `scenarios/new_england/*` | apply (NE39) | Out of Kundur scope |

These all hit the deprecated `apply_disturbance(...)` path; works identically to today, emits `DeprecationWarning` once per process (or per call, depending on `warnings.simplefilter` setting in caller).

---

## 5. R-1 to R-3 risk table (P4 implementation)

| ID | Risk | Trigger | Mitigation in code | P4 test |
|---|---|---|---|---|
| R-1 | Trigger time wrong (off-by-one in `_trigger_at_step` comparison) | step==2 vs step==1 firing → wrong post-warmup transient | Compare `_step_count == _trigger_at_step`; default = `int(0.5/DT)`; entry in step() BEFORE `_step_backend` call (so trigger fires for the action that takes the system from step 2 → step 3) | unit: 5-step rollout, assert disturbance writes appear before bridge.step() of step 2 |
| R-2 | Legacy + new patterns mixed → double-fire | `env.reset(scenario=...)` followed by `env.apply_disturbance(...)` would fire twice | `apply_disturbance` sets `_disturbance_triggered = True`; internal trigger checks the flag | unit: call both APIs in same episode, assert dispatch happens exactly once |
| R-3 | RNG order drift in train random path | `env.reset(options=...)` resolves no random; train still draws magnitude with `np.random.uniform` (module-level). RNG order matches legacy. | KEEP train's `np.random.uniform` call in the loop; only the apply path changes | smoke: 5-ep cold-start with same args.seed; assert mean_reward ±1% (M9) |
| R-4 | `_disturbance_type` external write breaks | Probes write `env._disturbance_type = ...` then call `apply_disturbance` | `_disturbance_type` stays as regular attr (not @property); both paths read it | manual: probe smoke (run `_phi_root_cause.py` 5 steps, assert no AttributeError) |
| R-5 | paper_eval byte-level diverges due to scenario translation | bus=7 → 'pm_step_proxy_bus7' translation; if order changes, paper_eval bytes drift | Translation is deterministic via existing `scenario_to_disturbance_type`; trigger_at_step=0 matches legacy timing exactly | smoke: paper_eval 1 ep with fixed `Scenario(kind='gen', target=2, mag=2.0)` byte-identical to legacy (M10) |
| R-6 | DeprecationWarning floods stderr in paper_eval | 50 episodes × N warning per episode → noisy log | paper_eval line 260's `apply_disturbance` is migrated to scenario+options path; no warning fires from paper_eval | grep paper_eval stderr for 0 DeprecationWarning |

---

## 6. P4 commit split

Per spec §3.1 P4: 2 commits.

**Commit 4a — env API**:
- `env/simulink/kundur_simulink_env.py`:
  - `reset()` signature: add `scenario`, parse `options['trigger_at_step']`
  - Add 4 instance attrs (`_episode_scenario`, `_episode_magnitude`, `_trigger_at_step`, `_disturbance_triggered`)
  - `step()` body: add internal trigger block at top
  - `apply_disturbance()`: add `DeprecationWarning` + `_disturbance_triggered = True`
- `tests/test_disturbance_protocols.py`: extend with R-1, R-2, R-4 unit tests
- Optionally: small new test file `tests/test_kundur_env_scenario_api.py` for the trigger semantics specifically
- 5-ep cold smoke (Y4) optional

**Commit 4b — call site migration**:
- `scenarios/kundur/train_simulink.py`:
  - Delete `_ep_disturbance` closure
  - Replace 5 `_disturbance_type =` writes
  - Delete `apply_disturbance` call from step loop
  - Migrate `evaluate()` function (line 276)
- `evaluation/paper_eval.py`:
  - Replace 5 `_disturbance_type =` writes with Scenario construction
  - Replace `apply_disturbance(magnitude=mag)` (line 260) with `env.reset(scenario=..., options={'trigger_at_step': 0})`
- 5-ep cold smoke (random + scenario_set)
- paper_eval 1-ep smoke

---

## 7. P4 acceptance gates (recap from spec §5.3)

- `pytest tests/` 全 green
- `grep -nE "env\\._disturbance_type\\s*="` in `scenarios/kundur/`, `evaluation/` → 0 hits (M3/M4)
- `train_simulink.py` 中无 `_ep_disturbance` 函数 (M5)
- 5-ep cold smoke ×2:
  - 模式 1: 随机 disturbance, ≤ ±1% on `mean_reward` + `max_freq_dev_hz` (M9)
  - 模式 2: `--scenario-set test`, 容差同上
- paper_eval 1-ep smoke: byte-level identical on §4.6 INCLUDED 字段 (M10)
- `monitor` 路径不变（events.jsonl, training_status.json schema）

---

## 8. 不在本设计内 (deferred)

- 不动 `Scenario` 字段（保持 scenario_loader 不变）
- 不动 `scenario_to_disturbance_type` 翻译表
- 不删除 `apply_disturbance` 公开 API（DeprecationWarning + 兼容）
- 不动 NE39 train_simulink（C4 仅 Kundur 范围）
- 不动 probes / scripts / tests / evaluate_simulink — legacy 路径保留
- 不动 `_disturbance_type` 字段类型（仍是 str instance attr，非 @property）
- 不改物理 effective_in_profile（仍 P0 ADR 锁定）

---

## 9. 进入 P4 的核心要求

P4 必须做到的 7 个事实：

1. `env.reset(scenario=Scenario(...))` 工作端到端：scenario → `_disturbance_type` + `_episode_magnitude` → step 内部 trigger
2. `env.reset(options={'disturbance_magnitude': mag, 'trigger_at_step': 0})` 工作（paper_eval 路径）
3. `env.reset(options={'disturbance_magnitude': mag})` 工作（train random 路径）
4. `env.apply_disturbance(...)` 仍可调用，发 DeprecationWarning 一次
5. R-1 到 R-6 测试覆盖
6. 5-ep cold smoke ×2 + paper_eval 1-ep smoke 通过 §4.6 deterministic oracle 验收
7. M3/M4/M5 grep 验证全 0 hits

P3 doc 完成。等待用户 review 后进入 P4 实现（commit 4a + 4b）。
