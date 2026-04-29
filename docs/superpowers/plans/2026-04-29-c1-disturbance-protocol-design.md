# P1 — C1 DisturbanceProtocol Design (no-code)

**Stage:** P1 of `quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`
**Date:** 2026-04-29
**Status:** DRAFT — awaiting user review before P2 entry
**Predecessor:** P0 commit `0af9813`
**No code changes in this stage.** Design only.

---

## 0. Baseline measurement

`env/simulink/kundur_simulink_env.py:_apply_disturbance_backend`:
- Function body (def line + docstring + body, line 789-1069) = **281 lines total**
- CVS branch only (line 814-1048) = **235 lines**
- SPS legacy fall-through branch (line 1050-1069) = **20 lines** — out of scope, left as-is in env

Target after C1: function body (CVS dispatch) ≤ 30 lines (soft) / ≤ 45 lines (hard cap, M2 spec).

---

## 1. 14 type → 4 adapter 归属表

Reading from the actual god method (line 814-1048). Each row reports the exact behavior the new adapter MUST reproduce byte-level.

### 1.1 Family A — `EssPmStepProxy` (4 types)

Ess Pm-step proxy: writes `PM_STEP_AMP[target_indices]` at sys-pu, zeros all other ESS PM_STEP and all SG PMG_STEP.

| dtype | target_indices | RNG used? | magnitude semantic |
|---|---|---|---|
| `pm_step_proxy_bus7` | `(0,)` | no | divided by `n_tgt=1` (= magnitude) |
| `pm_step_proxy_bus9` | `(3,)` | no | divided by `n_tgt=1` (= magnitude) |
| `pm_step_proxy_random_bus` | `(0,)` or `(3,)` 50/50 | **yes** (`np_random.random()`) | divided by `n_tgt=1` (= magnitude) |
| `pm_step_single_vsg` (legacy default) | `tuple(self.DISTURBANCE_VSG_INDICES)`, default `(0,)` | no | divided by `n_tgt=len(target_indices)` |

**Workspace writes per dispatch:**
- For each `i in 1..n_agents`: `PM_STEP_T[i] := t_now`, `PM_STEP_AMP[i] := amps_per_vsg[i-1]` where `amps_per_vsg[idx] = magnitude/n_tgt` if `idx in target_indices` else 0.0
- For each `g in 1..3`: `PMG_STEP_T[g] := t_now`, `PMG_STEP_AMP[g] := 0.0`

**`require_effective`**: `False` (default; PM_STEP family is effective in v3 by definition).

**Logging**: `print` with sign / target list / per_vsg_amps / proxy_tag.

### 1.2 Family B — `SgPmgStepProxy` (4 types)

SG Pmg-step proxy: writes `PMG_STEP_AMP[target_g]` at sys-pu, zeros all other SG PMG_STEP and all ESS PM_STEP.

| dtype | target_g | RNG used? | magnitude semantic |
|---|---|---|---|
| `pm_step_proxy_g1` | 1 | no | full magnitude (sys-pu, verbatim) |
| `pm_step_proxy_g2` | 2 | no | full magnitude (sys-pu, verbatim) |
| `pm_step_proxy_g3` | 3 | no | full magnitude (sys-pu, verbatim) |
| `pm_step_proxy_random_gen` | uniform 1/2/3 | **yes** (`np_random.integers(1, 4)`) | full magnitude (sys-pu, verbatim) |

**Workspace writes per dispatch:**
- For each `g in 1..3`: `PMG_STEP_T[g] := t_now`, `PMG_STEP_AMP[g] := 0.0` (silence first)
- Then: `PMG_STEP_AMP[target_g] := magnitude` (set target — no `t_now` re-write here, because it was already set in silence loop)
- For each `i in 1..n_agents`: `PM_STEP_T[i] := t_now`, `PM_STEP_AMP[i] := 0.0`

**Note on write order**: silence-others happens BEFORE target set. P2 byte-level oracle must preserve this (an adapter that sets target THEN silences all G would zero its own write).

**`require_effective`**: `False` (PMG_STEP family is effective in v3).

**Logging**: `print` with sign / target / amp / step_time.

### 1.3 Family C — `LoadStepRBranch` (3 types)

LoadStep R-block dispatch: writes `LOAD_STEP_AMP[ls_bus]` to drive the Series RLC R block. Two semantically distinct actions sharing this family:
- **trip** (R disengage): IC has 248MW pre-engaged on bus14; write 0 to disengage. **`magnitude` IGNORED**.
- **engage** (R engage): IC has 0MW on bus15; write `abs(magnitude) * sbase_va` to engage.

| dtype | ls_bus_label | ls_action | RNG used? | magnitude semantic |
|---|---|---|---|---|
| `loadstep_paper_bus14` | bus14 | trip | no | **IGNORED** (always full 248MW IC) |
| `loadstep_paper_bus15` | bus15 | engage | no | `abs(magnitude) * sbase_va` (watts) |
| `loadstep_paper_random_bus` | bus14 (50%) or bus15 (50%) | trip if bus14, engage if bus15 | **yes** (`np_random.random()`) | per-bus (IGNORED on bus14, abs×sbase on bus15) |

**Workspace writes per dispatch (trip branch, ls_bus = 14)**:
- `LOAD_STEP_AMP[14] := 0.0`
- `LOAD_STEP_TRIP_AMP[14] := 0.0`
- `LOAD_STEP_TRIP_AMP[15] := 0.0`  (other bus zeroed)
- `LOAD_STEP_AMP[15]` **NOT touched** (stays at IC = 0)
- For each `i in 1..n_agents`: `PM_STEP_T[i] := t_now`, `PM_STEP_AMP[i] := 0.0`
- For each `g in 1..3`: `PMG_STEP_T[g] := t_now`, `PMG_STEP_AMP[g] := 0.0`

**Workspace writes per dispatch (trip branch, ls_bus = 15)**:
- `LOAD_STEP_AMP[15] := 0.0`
- `LOAD_STEP_TRIP_AMP[15] := 0.0`, `LOAD_STEP_TRIP_AMP[14] := 0.0`
- `LOAD_STEP_AMP[14]` **NOT touched** (stays at IC = 248e6)
- + ESS/SG silence (same as above)

**Workspace writes per dispatch (engage branch, ls_bus = 15)**:
- `LOAD_STEP_AMP[15] := abs(magnitude) * sbase_va`
- `LOAD_STEP_TRIP_AMP[15] := 0.0`, `LOAD_STEP_TRIP_AMP[14] := 0.0`
- `LOAD_STEP_AMP[14]` **NOT touched** (stays at IC = 248e6)
- + ESS/SG silence

**Workspace writes per dispatch (engage branch, ls_bus = 14)** — never reached by current dtype map but adapter must support symmetric for tests:
- `LOAD_STEP_AMP[14] := abs(magnitude) * sbase_va`
- `LOAD_STEP_TRIP_AMP[14] := 0.0`, `LOAD_STEP_TRIP_AMP[15] := 0.0`
- `LOAD_STEP_AMP[15]` **NOT touched** (stays at IC = 0)
- + ESS/SG silence

**`require_effective`**: `True` (LOAD_STEP_AMP / LOAD_STEP_TRIP_AMP are name-valid but not physically-effective in v3 due to R compile-freeze; current code uses `require_effective=True` to surface contract violation rather than silently no-op).

**Logging**: `logger.info` with action / ls_bus_label / amp_w in MW / magnitude / step_time.

### 1.4 Family D — `LoadStepCcsInjection` (3 types)

CCS injection: writes `LOAD_STEP_TRIP_AMP[ls_bus]`. Phase A++ alternate (not paper main path). All variants use `cc_inject` action.

| dtype | ls_bus_label | RNG used? | magnitude semantic |
|---|---|---|---|
| `loadstep_paper_trip_bus14` | bus14 | no | `abs(magnitude) * sbase_va` (watts) |
| `loadstep_paper_trip_bus15` | bus15 | no | `abs(magnitude) * sbase_va` (watts) |
| `loadstep_paper_trip_random_bus` | bus14 (50%) or bus15 (50%) | **yes** (`np_random.random()`) | `abs(magnitude) * sbase_va` |

**Workspace writes per dispatch (e.g. ls_bus = 14)**:
- `LOAD_STEP_TRIP_AMP[14] := abs(magnitude) * sbase_va`
- `LOAD_STEP_TRIP_AMP[15] := 0.0`
- `LOAD_STEP_AMP` **NOT touched** (both buses stay at IC)
- + ESS/SG silence (same as Family C)

**`require_effective`**: `True` (CCS path is name-valid but signal ~0.01 Hz on Bus 14/15 ESS terminals — not paper-grade).

**Logging**: `logger.info` (same template as Family C, with action='cc_inject').

---

## 2. Protocol 接口签名

Per spec §4.1 (RNG injection (a)):

```python
from typing import Protocol
import numpy as np
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DisturbanceTrace:
    """Record of one dispatch — for monitoring + tests, not for control flow."""
    family: str                                   # 'ess_pm_step' / 'sg_pmg_step' / 'load_step_r' / 'load_step_ccs'
    target_descriptor: str                        # e.g. "VSG[0]", "SG[2]", "bus14:trip", "bus15:engage"
    written_keys: tuple[str, ...] = field(default_factory=tuple)   # full MATLAB var names actually written, in order
    written_values: tuple[float, ...] = field(default_factory=tuple)  # corresponding values
    magnitude_sys_pu: float = 0.0                 # original magnitude (for log)


class DisturbanceProtocol(Protocol):
    """One disturbance family. Stateless — RNG and bridge passed per call."""
    def apply(
        self,
        bridge,                                   # SimulinkBridge (typed loosely to avoid import cycle in tests)
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg,                                      # BridgeConfig
    ) -> DisturbanceTrace: ...
```

**Why no `apply_workspace_var` plumbing in the Protocol**: the adapter calls `bridge.apply_workspace_var(name, value)` directly. Tests use a fake bridge that records calls.

**Why `magnitude_sys_pu` not `magnitude`**: makes the unit explicit at the type level.

**Why `t_now` is a parameter**: the env passes `self.bridge.t_current` once; adapters don't re-fetch (avoids hidden bridge access during dispatch).

**Why `cfg` is passed**: adapters need `cfg.sbase_va` (LoadStep watts conversion) and `cfg.n_agents` (PM_STEP/PMG_STEP silence loops). They MUST NOT mutate `cfg`.

---

## 3. Adapter 内部状态 (constructor parameters)

```python
@dataclass(frozen=True)
class EssPmStepProxy:
    """Family A. Writes PM_STEP_AMP for target_indices; silences other PM and all PMG."""
    target_indices: tuple[int, ...] | str        # tuple of 0-indexed VSG ids OR "random_bus" sentinel OR "single_vsg" sentinel
    proxy_bus: int | None = None                 # 7 / 9 / None — for log only

@dataclass(frozen=True)
class SgPmgStepProxy:
    """Family B. Writes PMG_STEP_AMP for target_g; silences other PMG and all PM."""
    target_g: int | str                          # 1 / 2 / 3 OR "random_gen" sentinel

@dataclass(frozen=True)
class LoadStepRBranch:
    """Family C. R-block disengage (trip) or engage."""
    ls_bus: int | str                            # 14 / 15 OR "random_bus" sentinel
    # action is derived: bus14 -> trip, bus15 -> engage. random_bus -> 50/50 over (14,trip) and (15,engage).

@dataclass(frozen=True)
class LoadStepCcsInjection:
    """Family D. CCS injection on ls_bus."""
    ls_bus: int | str                            # 14 / 15 OR "random_bus" sentinel
```

**Why frozen dataclass**: adapters are immutable value objects; safe to share across episodes; trivially hashable for use as dict key in tests.

**Why string sentinels for random**: `target_indices=(0,3)` would mean "spread to both" (legitimate semantic for `single_vsg` with 2 indices). To distinguish "random pick of {0} or {3}" we use the sentinel `"random_bus"`. Same for `random_gen`. Sentinels are checked in `apply()`: if `isinstance(target_indices, str)` then resolve via `rng`.

**Why `single_vsg` is a sentinel**: `pm_step_single_vsg` reads `self.DISTURBANCE_VSG_INDICES` from the env, not from the adapter. The sentinel signals "look up DISTURBANCE_VSG_INDICES at apply time"; the resolver factory reads `env` at construction time and binds the tuple, OR the `apply()` signature takes an extra `vsg_indices_override` (cleaner: factory binds at construction).

---

## 4. Resolver factory

```python
_DISPATCH_TABLE: dict[str, Callable[..., DisturbanceProtocol]] = {
    'pm_step_proxy_bus7':           lambda: EssPmStepProxy(target_indices=(0,), proxy_bus=7),
    'pm_step_proxy_bus9':           lambda: EssPmStepProxy(target_indices=(3,), proxy_bus=9),
    'pm_step_proxy_random_bus':     lambda: EssPmStepProxy(target_indices="random_bus"),
    'pm_step_single_vsg':           lambda vsg_indices: EssPmStepProxy(
                                       target_indices=tuple(vsg_indices)),
    'pm_step_proxy_g1':             lambda: SgPmgStepProxy(target_g=1),
    'pm_step_proxy_g2':             lambda: SgPmgStepProxy(target_g=2),
    'pm_step_proxy_g3':             lambda: SgPmgStepProxy(target_g=3),
    'pm_step_proxy_random_gen':     lambda: SgPmgStepProxy(target_g="random_gen"),
    'loadstep_paper_bus14':         lambda: LoadStepRBranch(ls_bus=14),
    'loadstep_paper_bus15':         lambda: LoadStepRBranch(ls_bus=15),
    'loadstep_paper_random_bus':    lambda: LoadStepRBranch(ls_bus="random_bus"),
    'loadstep_paper_trip_bus14':    lambda: LoadStepCcsInjection(ls_bus=14),
    'loadstep_paper_trip_bus15':    lambda: LoadStepCcsInjection(ls_bus=15),
    'loadstep_paper_trip_random_bus': lambda: LoadStepCcsInjection(ls_bus="random_bus"),
}


def resolve_disturbance(
    disturbance_type: str,
    *,
    vsg_indices: tuple[int, ...] | None = None,  # for pm_step_single_vsg only
) -> DisturbanceProtocol:
    """Return the adapter instance for a disturbance_type string."""
    if disturbance_type == 'pm_step_single_vsg':
        if vsg_indices is None:
            vsg_indices = (0,)
        return EssPmStepProxy(target_indices=tuple(vsg_indices))
    factory = _DISPATCH_TABLE.get(disturbance_type)
    if factory is None:
        raise ValueError(
            f"unknown disturbance_type {disturbance_type!r}; "
            f"valid: {sorted(_DISPATCH_TABLE)}"
        )
    return factory()
```

**Caller (the env) becomes**:

```python
def _apply_disturbance_backend(self, bus_idx, magnitude):
    cfg = self.bridge.cfg
    if cfg.model_name in ('kundur_cvs', 'kundur_cvs_v3'):
        dtype = getattr(self, '_disturbance_type', 'pm_step_single_vsg')
        protocol = resolve_disturbance(
            dtype,
            vsg_indices=getattr(self, 'DISTURBANCE_VSG_INDICES', None),
        )
        protocol.apply(
            bridge=self.bridge,
            magnitude_sys_pu=float(magnitude),
            rng=self.np_random,
            t_now=float(self.bridge.t_current),
            cfg=cfg,
        )
        return
    # SPS legacy fall-through (line 1050-1069 unchanged, ~20 lines)
    ...
```

This collapses CVS dispatch from 235 lines to ~10. SPS legacy stays ~20 lines. Total `_apply_disturbance_backend` body ≤ 30 lines (M2 soft target).

---

## 5. 风险表

Risks of mis-extraction. Each row carries an explicit acceptance signal in P2.

| ID | Risk | Trigger | Mitigation in adapter | Test fixture |
|---|---|---|---|---|
| R-A | LS1 IGNORE magnitude lost (LoadStepRBranch.trip uses magnitude when it shouldn't) | adapter writes `abs(magnitude)*sbase_va` to bus14 instead of `0.0` | LoadStepRBranch.trip branch hard-codes `LOAD_STEP_AMP[ls_bus] := 0.0`, `magnitude_sys_pu` only enters the trace, not the write | test: `dtype=loadstep_paper_bus14, magnitude=±5.0` → `LOAD_STEP_AMP[14] == 0.0` |
| R-B | LS2 sign flipped (forget `abs()`) | adapter writes negative `LOAD_STEP_AMP[15]` for negative magnitude | LoadStepRBranch.engage uses `abs(magnitude_sys_pu) * cfg.sbase_va` | test: `dtype=loadstep_paper_bus15, magnitude=-3.0` → `LOAD_STEP_AMP[15] == 3.0 * sbase_va` (positive) |
| R-C | SgPmgStep silence-then-set order reversed | adapter sets target first, then silence loop overwrites it to 0 | Apply MUST silence all g first, then set target g | test: `dtype=pm_step_proxy_g2, magnitude=+1.0` → final `PMG_STEP_AMP[2] == 1.0` (not 0.0) |
| R-D | Pm-step magnitude divided/not-divided wrong | adapter uses `magnitude / n_tgt` for SG (correct: full) or `magnitude` for ESS (correct: divided) | EssPmStep divides by `len(target_indices)`; SgPmgStep does not divide | test: `dtype=pm_step_single_vsg with VSG_INDICES=(0,1,2,3), magnitude=4.0` → each VSG gets `1.0`. `dtype=pm_step_proxy_g1, magnitude=4.0` → SG[1] gets `4.0` |
| R-E | RNG source wrong (uses `np.random` module-level instead of injected `rng`) | adapter is non-reproducible across env seeds | Adapter signature **only** accepts `rng`; static check via `grep -n "np\.random\." scenarios/kundur/disturbance_protocols.py` should return 0 (apart from imports) | test: `random_bus` adapter with two different rng seeds → different selections |
| R-F | "Silence others" set incomplete (forget PMG when in ESS path or vice-versa) | next-episode dispatch reads stale workspace value | Each adapter explicitly silences both other-family vars in its `apply()` body. Trace `written_keys` MUST include the silence writes | test: count of writes per dispatch matches god-method count exactly |
| R-G | LS engage on bus14 untested → adapter has hidden bug | symmetric path may diverge when paper extends bus14 engage | LoadStepRBranch.apply supports both (bus, action) combos cleanly even though dtype map only uses (14,trip), (15,engage). Test exercises (14, engage) and (15, trip) symmetric cases for completeness | test: `LoadStepRBranch(ls_bus=14)` with action overridden → engage path |
| R-H | `random_bus` sentinel in EssPmStepProxy resolves to wrong tuple | adapter picks (1,) or (2,) instead of (0,) or (3,) | "random_bus" sentinel resolves to `(0,)` or `(3,)` 50/50 (matching env line 1010-1015) | test: 1000-sample run, distribution of target_indices is ≈ 50/50 between (0,) and (3,) |
| R-I | Trace incomplete (missing key/value pair) | tests pass on visible writes but mutator regression is silent | `DisturbanceTrace.written_keys` and `written_values` are tuples set by adapter; len consistency assertion in tests | test: `len(trace.written_keys) == len(trace.written_values)` for every type |
| R-J | `_disturbance_type` default lookup chain breaks | env without env-var set falls back to wrong dtype | `getattr(self, '_disturbance_type', 'pm_step_single_vsg')` preserved verbatim; resolver default also maps `pm_step_single_vsg` → `EssPmStepProxy(target_indices=(0,))` | test: env with no `_disturbance_type` set → resolver picks single_vsg; protocol writes `PM_STEP_AMP[0]` only |

---

## 6. 验收（P2 进入条件）

**P1 出口**:
- [ ] User reviews this design doc
- [ ] User confirms 14→4 attribution table is correct
- [ ] User confirms Protocol signature
- [ ] User approves R-A through R-J risk mitigations
- [ ] (Optional) User flags any constraint not captured

**P2 入口** (after P1 approved):
- 新文件 `scenarios/kundur/disturbance_protocols.py` 实现 §2-§4 of this doc
- 新文件 `tests/test_disturbance_protocols.py` 覆盖 §5 的每条 R-*
- env `_apply_disturbance_backend` CVS 分支收缩到 §4 给出的 ~10 行结构
- (Y1) `tests/_disturbance_backend_legacy.py` 保存当前 god method 拷贝作字节级 oracle，P4 完成后删除

---

## 7. 不在本设计范围内 (deferred)

- Bridge.warmup 写 `kundur_cvs_ip` struct — 仍是 bare-string, 不动 (C2 territory)
- `BridgeConfig` 字段重构 — C2 territory
- SPS legacy 分支 (line 1050-1069 of env) — 保留为 fall-through, 不进 protocol 层
- NE39 disturbance dispatch — 不动
- Effective_in_profile 集合 — 仅靠物理修复推进 (P0 ADR 锁定)
- `DISTURBANCE_VSG_INDICES` class attr — 保留作为 single_vsg 配置入口；adapter 仅消费

---

## 8. 进入 P2 的核心要求

P2 必须做到的 6 个事实:

1. CVS dispatch 分支函数体行数 ≤ 30 (soft) / ≤ 45 (hard, 解释)
2. 14 个 disturbance_type 的字节级 write log 与 god method 一致 (oracle = `tests/_disturbance_backend_legacy.py`)
3. R-A 到 R-J 各有至少一个测试 case
4. 跨 v2/v3 profile 不修改 adapter 行为 (CVS 分支条件 `cfg.model_name in ('kundur_cvs', 'kundur_cvs_v3')` 不变)
5. SPS legacy fall-through 行为 byte-level 不变
6. `tests/test_kundur_workspace_vars.py` 60/60 仍 PASS (无 schema 回归)

P1 doc 完成。等待用户 review 后进入 P2 实现。
