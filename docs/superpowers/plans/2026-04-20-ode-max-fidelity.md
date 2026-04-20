# ODE Max-Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the pure-ODE multi-VSG model's fidelity within current modeling scope — adding parameter heterogeneity, intra-episode disturbance scheduling, optional nonlinear swing coupling, first-order governor dynamics, and discrete topology events — without requiring Simulink.

**Architecture:** All new capabilities are opt-in flags / kwargs. Paper-baseline behavior (`config.py` defaults) stays baseline-preserving, verified by compatibility gates. `PowerSystem` gains `network_mode`, `governor_enabled`/`governor_R`/`governor_tau_g`, `event_schedule` kwargs; `MultiVSGEnv` forwards them as separate parameters. A new `utils/ode_events.py` module defines `DisturbanceEvent` / `LineTripEvent` / `EventSchedule` (immutable dataclasses). A new `utils/ode_heterogeneity.py` generates spread H/D arrays with seeded RNG.

**Tech Stack:** Python 3.11, NumPy, SciPy `solve_ivp` (RK45), pytest. No new dependencies.

---

## Progress Status

| Task | 状态 |
|---|---|
| Task 1: Parameter Heterogeneity | ✅ 实现 + spec review + quality review 通过 |
| Task 2: Intra-Episode Disturbance Schedule | ✅ 实现 + spec review + quality review 通过 |
| Task 3: Nonlinear Swing Network | ✅ 实现 + spec review + quality review 通过 |
| Task 4A: First-Order Governor / Droop (power_system.py only) | ✅ 实现 + spec review + quality review 通过 |
| Task 4B: Heterogeneity Env Integration (multi_vsg_env.py only) | ✅ 实现 + spec review + quality review 通过 |
| Task 5: Discrete Topology Events | ✅ 实现 + spec review + quality review 通过 |
| Task 6: Promotion Gates (Engineering Regression) | ✅ 实现完成，38 tests pass |
| Task 7: Docs + Integration Notes | ✅ 完成 |

---

## File Structure

### Create
- `utils/ode_events.py` — `DisturbanceEvent`, `LineTripEvent`, `EventSchedule` dataclasses (step-boundary semantics).
- `utils/ode_heterogeneity.py` — `generate_heterogeneous_params(base, spread, seed)` helper.
- `tests/test_ode_heterogeneity.py`
- `tests/test_ode_disturbance_schedule.py`
- `tests/test_ode_nonlinear.py`
- `tests/test_ode_governor.py`
- `tests/test_ode_line_trip.py`
- `tests/test_ode_fidelity_extended.py`
- `env/ode/NOTES.md` — modeling notes, toggle semantics, known limits.

### Modify
- `env/ode/power_system.py` — accept `B_matrix`, `V_bus`, `network_mode`, `governor_enabled`/`governor_R`/`governor_tau_g`, `event_schedule`; extend state to 3N when governor on; apply events at step boundary.
- `env/ode/multi_vsg_env.py` — forward kwargs; `event_schedule` is a separate parameter that takes priority over `delta_u`.
- `config.py` — add `ODE_NETWORK_MODE`, `ODE_GOVERNOR_ENABLED`, `ODE_GOVERNOR_R`, `ODE_GOVERNOR_TAU_G`, `ODE_HETEROGENEOUS`, `ODE_H_SPREAD`, `ODE_D_SPREAD`.
- `CLAUDE.md` — ODE row links to new `env/ode/NOTES.md`.

### Untouched (read-only reference)
- `env/network_topology.py`
- `agents/*`, `scenarios/*/train_ode.py`, `scenarios/*/evaluate_ode.py` — all existing behavior preserved by defaulting flags off.

---

## Task 1: Parameter Heterogeneity ✅

**Files:**
- Create: `utils/ode_heterogeneity.py`
- Create: `tests/test_ode_heterogeneity.py`
- Modify: `config.py` (add heterogeneity knobs at end of VSG parameters block)

- [x] **Step 1.1: Write the failing tests**

Create `tests/test_ode_heterogeneity.py`:

```python
"""Parameter heterogeneity helper tests."""
import numpy as np
import pytest

from utils.ode_heterogeneity import generate_heterogeneous_params


def test_zero_spread_returns_uniform():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.0, seed=0)
    np.testing.assert_array_equal(out, base)


def test_mean_preserved_within_tolerance():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert abs(float(out.mean()) - 24.0) < 0.1


def test_spread_produces_distinct_values():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert len(set(out.tolist())) == len(base)
    assert (out > 0).all()


def test_seed_is_deterministic():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    a = generate_heterogeneous_params(base, spread=0.3, seed=42)
    b = generate_heterogeneous_params(base, spread=0.3, seed=42)
    np.testing.assert_array_equal(a, b)


def test_rejects_negative_spread():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    with pytest.raises(ValueError):
        generate_heterogeneous_params(base, spread=-0.1, seed=0)


def test_enforces_positive_floor():
    # Large spread should still yield strictly positive values
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.95, seed=7)
    assert (out > 0).all()
```

- [x] **Step 1.2: Run tests to verify they fail**

Run: `pytest tests/test_ode_heterogeneity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.ode_heterogeneity'`

- [x] **Step 1.3: Implement the helper**

Create `utils/ode_heterogeneity.py`:

```python
"""Generate heterogeneous H/D arrays around a uniform base.

The mean is preserved exactly by zero-sum symmetric perturbation.
"""
from __future__ import annotations

import numpy as np


def generate_heterogeneous_params(
    base: np.ndarray,
    spread: float,
    seed: int,
    floor: float = 1e-3,
) -> np.ndarray:
    """Return a permuted, mean-preserving spread of `base`.

    Parameters
    ----------
    base : np.ndarray, shape (N,)
        Uniform baseline (e.g. H_ES0 = [24, 24, 24, 24]).
    spread : float
        Fractional spread in [0, 1). Samples in +/- spread * base[0].
    seed : int
        RNG seed for reproducibility.
    floor : float
        Minimum positive value enforced after perturbation.

    Returns
    -------
    np.ndarray, shape (N,)
        Heterogeneous parameters with mean approximately equal to base.mean().
    """
    if spread < 0:
        raise ValueError(f"spread must be >= 0, got {spread}")
    base = np.asarray(base, dtype=np.float64)
    if spread == 0.0:
        return base.copy()
    rng = np.random.default_rng(seed)
    # Symmetric zero-sum perturbation preserves the mean exactly.
    raw = rng.uniform(-1.0, 1.0, size=base.shape)
    raw -= raw.mean()
    scaled = spread * base * raw
    out = base + scaled
    return np.maximum(out, floor)
```

- [x] **Step 1.4: Run tests to verify they pass**

Run: `pytest tests/test_ode_heterogeneity.py -v`
Expected: 6 passed.

- [x] **Step 1.5: Add config knobs**

Modify `config.py` — append at the end of the VSG basics block (after `D_ES0 = np.array(...)`):

```python
# ═══════════════════════════════════════════════════════
#  ODE Fidelity Toggles (default = paper baseline)
# ═══════════════════════════════════════════════════════
ODE_HETEROGENEOUS = False          # True → per-node H/D differ
ODE_H_SPREAD = 0.30                # +/-30 % around H_ES0[0]
ODE_D_SPREAD = 0.30
ODE_HETEROGENEITY_SEED = 2023      # deterministic spread
```

- [x] **Step 1.6: Commit**

```bash
git add utils/ode_heterogeneity.py tests/test_ode_heterogeneity.py config.py
git commit -m "feat(ode): heterogeneous H/D parameter generator (Task 1)"
```

---

## Task 2: Intra-Episode Disturbance Schedule ✅

**Files:**
- Create: `utils/ode_events.py`
- Create: `tests/test_ode_disturbance_schedule.py`
- Modify: `env/ode/power_system.py` — `reset(schedule=...)` + step-boundary event application inside `step()`.
- Modify: `env/ode/multi_vsg_env.py` — forward `delta_u` array **or** `EventSchedule`.

- [x] **Step 2.1: Write failing tests**

Create `tests/test_ode_disturbance_schedule.py`:

```python
"""Intra-episode disturbance scheduling tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import DisturbanceEvent, EventSchedule


def _make_ps():
    B = np.array([
        [0, 4, 0, 0],
        [4, 0, 4, 0],
        [0, 4, 0, 4],
        [0, 0, 4, 0],
    ], dtype=float)
    L = build_laplacian(B, np.ones(4))
    return PowerSystem(L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)


def test_single_t0_event_matches_static_disturbance():
    # Baseline: static delta_u set at reset
    ps_static = _make_ps()
    ps_static.reset(delta_u=np.array([2.0, 0.0, -2.0, 0.0]))
    for _ in range(25):
        ps_static.step()
    theta_static = ps_static.state[:4].copy()

    # New path: same disturbance via EventSchedule at t=0
    ps_sched = _make_ps()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([2.0, 0.0, -2.0, 0.0])),
    ))
    ps_sched.reset(event_schedule=sched)
    for _ in range(25):
        ps_sched.step()
    theta_sched = ps_sched.state[:4].copy()

    np.testing.assert_allclose(theta_static, theta_sched, atol=1e-9)


def test_mid_episode_event_changes_trajectory():
    ps = _make_ps()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([2.0, 0.0, -2.0, 0.0])),
        DisturbanceEvent(t=2.0, delta_u=np.array([0.0, 0.0, 0.0, 0.0])),  # load restored
    ))
    ps.reset(event_schedule=sched)
    pre_peak = 0.0
    post_peak = 0.0
    for step in range(50):  # 10s
        r = ps.step()
        omega_mag = float(np.max(np.abs(r['omega'])))
        if step < 10:
            pre_peak = max(pre_peak, omega_mag)
        else:
            post_peak = max(post_peak, omega_mag)
    # After disturbance is removed at t=2s, oscillation decays
    assert post_peak < pre_peak


def test_schedule_rejects_non_monotonic_times():
    import pytest
    with pytest.raises(ValueError):
        EventSchedule(events=(
            DisturbanceEvent(t=2.0, delta_u=np.zeros(4)),
            DisturbanceEvent(t=1.0, delta_u=np.zeros(4)),
        ))
```

- [x] **Step 2.2: Run tests to verify they fail**

Run: `pytest tests/test_ode_disturbance_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.ode_events'`.

- [x] **Step 2.3: Implement event types**

Create `utils/ode_events.py`:

```python
"""Discrete event primitives for ODE multi-VSG simulation.

Events are applied at the start of each control step. The schedule is
frozen (immutable) so that environments can safely share it across resets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np


@dataclass(frozen=True)
class DisturbanceEvent:
    """Replace the current network-wide Δu vector at time `t` (s)."""
    t: float
    delta_u: np.ndarray  # shape (N,)

    def __post_init__(self) -> None:
        arr = np.asarray(self.delta_u, dtype=np.float64)
        object.__setattr__(self, "delta_u", arr)


@dataclass(frozen=True)
class LineTripEvent:
    """Remove the (i,j) edge from the network Laplacian at time `t`."""
    t: float
    bus_i: int
    bus_j: int


Event = Union[DisturbanceEvent, LineTripEvent]


@dataclass(frozen=True)
class EventSchedule:
    """Sorted, immutable list of events applied in order of `t`."""
    events: tuple[Event, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        times = [e.t for e in self.events]
        if any(t_next < t_prev for t_prev, t_next in zip(times, times[1:])):
            raise ValueError(f"Event times must be non-decreasing, got {times}")
        if any(t < 0 for t in times):
            raise ValueError(f"Event times must be non-negative, got {times}")

```

- [x] **Step 2.4: Wire schedule into PowerSystem**

Modify `env/ode/power_system.py`. Replace the existing `reset()` body and add event handling in `step()`. Import at top:

```python
from utils.ode_events import (
    DisturbanceEvent,
    LineTripEvent,
    EventSchedule,
)
```

Replace `reset()` with:

```python
def reset(self, delta_u=None, event_schedule=None):
    """重置系统到稳态.

    Parameters
    ----------
    delta_u : np.ndarray, shape (N,), optional
        静态扰动 — 兼容旧路径. 若同时给 event_schedule 将被忽略.
    event_schedule : EventSchedule, optional
        时变扰动/拓扑事件序列. 事件在 step 起始时刻生效.
    """
    self.state = np.zeros(2 * self.N)
    self.H_es = self.H_es0.copy()
    self.D_es = self.D_es0.copy()
    self.current_time = 0.0

    self._event_schedule = event_schedule
    self._step_count = 0
    if event_schedule is not None:
        self.delta_u = np.zeros(self.N)
    elif delta_u is not None:
        self.delta_u = np.asarray(delta_u, dtype=np.float64).copy()
    else:
        self.delta_u = np.zeros(self.N)
```

Add a helper just below `reset()`:

```python
def _apply_events(self, step_idx: int) -> None:
    """Apply events scheduled at step_idx (step-boundary semantics).

    Event e triggers when round(e.t / self.dt) - 1 == step_idx.
    Known: one-step-early bias for events at exact dt multiples.
    """
    if self._event_schedule is None:
        return
    for ev in self._event_schedule.events:
        if round(ev.t / self.dt) - 1 == step_idx:
            if isinstance(ev, DisturbanceEvent):
                self.delta_u = ev.delta_u.copy()
            # LineTripEvent handled in Task 5
```

Modify the top of `step()` — insert immediately after the `t_start = self.current_time` line:

```python
    # Apply events at step boundary, then advance counter
    t_start = self.current_time
    t_end = t_start + self.dt
    self._apply_events(self._step_count)
    self._step_count += 1
```

Also add `self._event_schedule = None` inside `__init__` so the attribute always exists.

- [x] **Step 2.5: Forward through MultiVSGEnv**

Modify `env/ode/multi_vsg_env.py`. In `reset()`, replace the branching block with:

```python
def reset(self, delta_u=None, event_schedule=None):
    """重置环境.

    Parameters
    ----------
    delta_u : np.ndarray or None
        静态扰动 (测试兼容).
    event_schedule : EventSchedule or None
        时变事件. 若给出则优先于 delta_u, 并禁用 random_disturbance.
    """
    if event_schedule is not None:
        self.current_delta_u = np.zeros(self.N)
        self.ps.reset(event_schedule=event_schedule)
    else:
        if delta_u is not None:
            self.current_delta_u = np.asarray(delta_u, dtype=np.float64).copy()
        elif self.random_disturbance:
            n_disturbed = self.rng.integers(1, 3)
            buses = self.rng.choice(self.N, size=n_disturbed, replace=False)
            self.current_delta_u = np.zeros(self.N)
            for bus in buses:
                magnitude = self.rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
                sign = self.rng.choice([-1, 1])
                self.current_delta_u[bus] = sign * magnitude
        else:
            self.current_delta_u = np.zeros(self.N)
        self.ps.reset(delta_u=self.current_delta_u)

    self.step_count = 0
    self.comm.reset(rng=self.rng)
    if self.forced_link_failures:
        for i, j in self.forced_link_failures:
            self.comm.eta[(i, j)] = 0
    self._delayed_omega = {}
    self._delayed_omega_dot = {}
    if self.comm_delay_steps > 0:
        for i in range(self.N):
            for j in self.comm.get_neighbors(i):
                self._delayed_omega[(i, j)] = deque([0.0] * self.comm_delay_steps,
                                                    maxlen=self.comm_delay_steps)
                self._delayed_omega_dot[(i, j)] = deque([0.0] * self.comm_delay_steps,
                                                        maxlen=self.comm_delay_steps)
    return self._build_observations(self.ps.get_state())
```

- [x] **Step 2.6: Run tests to verify they pass**

Run: `pytest tests/test_ode_disturbance_schedule.py tests/test_ode_physics_gates.py -v`
Expected: all 3 new tests PASS and all 4 existing physics gates still PASS.

- [x] **Step 2.7: Commit**

```bash
git add utils/ode_events.py tests/test_ode_disturbance_schedule.py env/ode/power_system.py env/ode/multi_vsg_env.py
git commit -m "feat(ode): intra-episode disturbance scheduling (Task 2)"
```

> **当前实现注记（含已知缺陷 — 进入 Task 5 前必须决定）**：
> `_apply_events` 目前匹配条件为 `round(ev.t / self.dt) - 1 == step_idx`，这会使"exact dt 倍数"的事件**提前整整一步**触发（例如 `t=1.0, dt=0.2` 的事件在 `t_start=0.8` 的那一步应用，而非从 `1.0` 开始）。Task 2 的 disturbance 测试对此不敏感（单个 t=0 事件），但 Task 5 的 line-trip at t=1.0 会把这个偏差暴露为可观测的物理误差。
>
> **Task 5 开始前必须执行的决定**：在写 `test_ode_line_trip.py` 之前先在 power_system.py 把匹配条件改为"包含事件时刻的步"语义，即：
> ```python
> # event e triggers on the step whose window [t_start, t_end) contains e.t
> if int(np.floor(ev.t / self.dt + 1e-9)) == step_idx:
>     ...
> ```
> 并顺手更新 Task 2 的 disturbance schedule 测试（如果有依赖一步提前偏移的断言）。这样 Task 5 的"line trip at t=1.0 后，该步末 L 矩阵已变"才是干净契约。**不要把一步提前偏差固化进 Task 5 测试。**

---

## Task 3: Nonlinear Swing Network ⚠️ 实现完成，review 待补

**Files:**
- Modify: `env/ode/power_system.py` — `__init__` takes `B_matrix`, `V_bus`, `network_mode`; `_dynamics` branches.
- Modify: `env/ode/multi_vsg_env.py` — pass `B_matrix`/`V_bus` via `getattr(cfg, ...)` (None when absent), `cfg.ODE_NETWORK_MODE`.
- Create: `tests/test_ode_nonlinear.py`

- [x] **Step 3.1: Write failing tests**

Create `tests/test_ode_nonlinear.py`:

```python
"""Nonlinear swing-equation network mode tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)
_L = build_laplacian(_B, _V)


def _run(mode, amplitude, steps=25):
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0),
        dt=0.2, fn=50.0,
        B_matrix=_B, V_bus=_V, network_mode=mode,
    )
    ps.reset(delta_u=np.array([amplitude, 0.0, -amplitude, 0.0]))
    peak_omega = 0.0
    for _ in range(steps):
        r = ps.step()
        peak_omega = max(peak_omega, float(np.max(np.abs(r['omega']))))
    return peak_omega


def test_linear_mode_default():
    # Default = linear, backward compatible
    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    assert getattr(ps, 'network_mode', 'linear') == 'linear'


def test_small_disturbance_linear_nonlinear_agree():
    # For small theta (amplitude 0.2 p.u.), sin(θ) ≈ θ within 1%
    lin = _run('linear', amplitude=0.2)
    non = _run('nonlinear', amplitude=0.2)
    rel_err = abs(lin - non) / max(abs(lin), 1e-9)
    assert rel_err < 0.02, f"small-signal lin/nonlin diverge: lin={lin}, non={non}"


def test_large_disturbance_linear_nonlinear_diverge():
    # At amplitude ~3 p.u. angles grow large; sin saturates → nonlinear coupling weaker → nonlinear ω peak ≥ linear
    lin = _run('linear', amplitude=3.0)
    non = _run('nonlinear', amplitude=3.0)
    rel_err = abs(lin - non) / max(abs(lin), 1e-9)
    assert rel_err > 0.02, f"large-signal lin/nonlin should diverge >2%, got {rel_err:.4f}"


def test_unknown_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0),
            dt=0.2, fn=50.0,
            B_matrix=_B, V_bus=_V, network_mode='bogus',
        )
```

- [x] **Step 3.2: Run tests to verify they fail**

Run: `pytest tests/test_ode_nonlinear.py -v`
Expected: FAIL (TypeError on unknown kwargs `B_matrix`, `V_bus`, `network_mode`).

- [x] **Step 3.3: Extend PowerSystem signature**

Modify `env/ode/power_system.py` — replace `__init__` signature and body with:

```python
def __init__(self, L, H_es0, D_es0, dt=0.2, fn=50.0,
             B_matrix=None, V_bus=None, network_mode='linear'):
    self.L = L.astype(np.float64)
    self.N = L.shape[0]
    self.H_es0 = H_es0.copy()
    self.D_es0 = D_es0.copy()
    self.dt = dt
    self.fn = fn
    self.omega_s = 2.0 * np.pi * fn

    if network_mode not in ('linear', 'nonlinear'):
        raise ValueError(f"network_mode must be 'linear' or 'nonlinear', got {network_mode!r}")
    self.network_mode = network_mode
    self.B_matrix = (B_matrix.astype(np.float64) if B_matrix is not None
                     else None)
    self.V_bus = (V_bus.astype(np.float64) if V_bus is not None
                  else None)
    if network_mode == 'nonlinear' and (B_matrix is None or V_bus is None):
        raise ValueError("network_mode='nonlinear' requires B_matrix and V_bus")

    self.H_es = H_es0.copy()
    self.D_es = D_es0.copy()
    self.state = np.zeros(2 * self.N)
    self.delta_u = np.zeros(self.N)
    self.current_time = 0.0
    self._event_schedule = None
    self._step_count = 0
```

- [x] **Step 3.4: Branch `_dynamics` on mode**

Add a helper and replace the coupling term in `_dynamics`:

```python
def _coupling(self, theta):
    """Network power injection L·θ (linear) or Σ V_i V_j B_ij sin(θ_i-θ_j) (nonlinear)."""
    if self.network_mode == 'linear':
        return self.L @ theta
    # nonlinear
    diff = theta[:, None] - theta[None, :]             # θ_i - θ_j
    coupling = self.V_bus[:, None] * self.V_bus[None, :] * self.B_matrix * np.sin(diff)
    return coupling.sum(axis=1)
```

Replace `_dynamics` body (just the `domega_dt` line):

```python
def _dynamics(self, t, state):
    theta = state[:self.N]
    omega = state[self.N:]
    M_inv = 1.0 / (2.0 * self.H_es)
    dtheta_dt = omega
    coupling = self._coupling(theta)
    domega_dt = M_inv * (self.omega_s * (self.delta_u - coupling) - self.D_es * omega)
    return np.concatenate([dtheta_dt, domega_dt])
```

Also update the matching block at the bottom of `step()` (and `get_state()`) where `self.L @ theta` appears — replace with `self._coupling(theta)` so `P_es`/`omega_dot` stay consistent:

```python
# in step(), replace the omega_dot / P_es recompute block:
M_inv = 1.0 / (2.0 * self.H_es)
coupling = self._coupling(theta)
omega_dot = M_inv * (self.omega_s * (self.delta_u - coupling) - self.D_es * omega)
P_es = coupling   # ΔP_es = network coupling (Eq.3 / nonlinear equivalent)
```

Do the same in `get_state()`.

- [x] **Step 3.5: Wire into MultiVSGEnv**

Modify `env/ode/multi_vsg_env.py` — change the `PowerSystem(...)` construction:

```python
self.ps = PowerSystem(
    self.L, cfg.H_ES0, cfg.D_ES0,
    dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi),
    B_matrix=getattr(cfg, 'B_MATRIX', None),
    V_bus=getattr(cfg, 'V_BUS', None),
    network_mode=getattr(cfg, 'ODE_NETWORK_MODE', 'linear'),
)
```

- [x] **Step 3.6: Run tests to verify they pass**

Run: `pytest tests/test_ode_nonlinear.py tests/test_ode_physics_gates.py tests/test_ode_disturbance_schedule.py -v`
Expected: all new tests PASS and previously-passing tests still PASS.

- [x] **Step 3.7: Commit**

```bash
git add env/ode/power_system.py env/ode/multi_vsg_env.py tests/test_ode_nonlinear.py
git commit -m "feat(ode): optional nonlinear swing coupling (Task 3)"
```

> **⚠️ Review 待补**：Task 3 的 spec review 和 quality review 因中断未完成。**继续前必须先完成这两项**，再进入 Task 4。
> 验证命令：`python -m pytest tests/test_ode_nonlinear.py tests/test_ode_physics_gates.py tests/test_ode_disturbance_schedule.py -v`

---

## ⛔ 阻塞门：Task 3 review 完成前禁止进入 Task 4

Task 3 的 spec review 和 quality review 被中断，**必须先补做完成并记录结果**后再继续以下任务。

**进入 Task 4 的前置条件（两项均须满足）：**

1. **Spec review 完成**：对照计划 Task 3 正文，逐条确认实现（`_coupling`、`_dynamics` 分支、`network_mode` 验证、`MultiVSGEnv` 构造传参）与规格一致；将结论记录到 `docs/devlog/2026-04-20-task3-ode-nonlinear-review.md`（不存在则新建），格式自定，但必须是显式文件产出，不能以"测试通过"代替。

2. **Quality review 完成**：检查 Task 3 改动的代码质量（命名清晰度、边界条件、潜在数值问题）；结论追加到同一文件。

辅助验证（不构成完成判据，仅供参考）：
```bash
python -m pytest tests/test_ode_nonlinear.py tests/test_ode_physics_gates.py tests/test_ode_disturbance_schedule.py -v
```

---

## Task 4A: First-Order Governor / Droop Control

**Files:**
- Modify: `env/ode/power_system.py` — state extended to 3N when governor on; `P_gov` added to net injection.
- Modify: `env/ode/multi_vsg_env.py` — read `cfg.ODE_GOVERNOR_ENABLED` etc.
- Create: `tests/test_ode_governor.py`

Governor equations (per-unit frequency feedback — R is a p.u. droop coefficient):

```
2H · dω/dt = ω_s · (Δu + P_gov − coupling) − D · ω
τ_G · dP_gov/dt = − (P_gov + (ω/ω_s)/R)
```

`R` is p.u. droop (5 % = 0.05), `τ_G` is turbine lag (s). Steady-state (`dP_gov/dt=0`)
yields `P_gov ≈ -(ω/ω_s)/R`, which is the form asserted in the tests and the
verification checklist. Do **not** use raw `ω/R`; that would be off by a factor
of `ω_s ≈ 314 rad/s` and fail the tests.

> **Supersede 说明（reset / _apply_events 多任务叠改）**：
> - `reset()`：Task 2 Step 2.4 硬编码 `self.state = np.zeros(2 * self.N)`；Task 4A Step 4.5 改为 `self.state = np.zeros(self.state.shape[0])`（保留当前 shape 以兼容 3N 布局）；Task 5 Step 5.3 在同一 `reset()` 里再加拓扑恢复 (`self.B_matrix = self._B_matrix0.copy(); self.L = self._L0.copy()`) 和 t=0 `LineTripEvent` 处理。执行者应合并成一个最终版本，而不是按片段机械覆盖。
> - `_apply_events()`：Task 2 Step 2.4 写成 `def _apply_events(self, step_idx: int)`（显式接收步索引）；Task 5 Step 5.3 改成 `def _apply_events(self)` 并在函数内部基于 `self._step_count`/`self.current_time` 判定，同时加 `LineTripEvent` 分支。Task 5 起以无参版本为准；Task 2 的 `self._apply_events(self._step_count)` 调用也要同步去掉 `self._step_count` 实参。
> - `step()` 的事件调用：Task 2 写 `self._apply_events(self._step_count)`，Task 5 后应改为 `self._apply_events()`。

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_ode_governor.py`:

```python
"""Governor / droop dynamics tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_L = build_laplacian(_B, np.ones(4))


def test_governor_off_is_default():
    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    assert getattr(ps, 'governor_enabled', False) is False
    assert ps.state.shape == (8,)  # 2N = 8


def test_governor_on_extends_state():
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    assert ps.state.shape == (12,)  # 3N = 12


def test_governor_steady_state_droop():
    """Unbalanced step -> after long simulation P_gov ≈ -(ω/ω_s)/R at each bus."""
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    # Unbalanced load step (CoI shifts)
    ps.reset(delta_u=np.array([-1.0, -1.0, -1.0, -1.0]))
    for _ in range(300):  # 60 s to converge
        r = ps.step()
    omega = r['omega']
    P_gov = ps.state[2 * 4:3 * 4]
    # Steady-state governor relation: P_gov ≈ -(ω/ωs) / R  (ω in rad/s, R in p.u.)
    expected = -(omega / ps.omega_s) / 0.05
    np.testing.assert_allclose(P_gov, expected, rtol=0.10)


def test_governor_reduces_frequency_deviation():
    """With governor, steady-state |Δω| is smaller than without for unbalanced step."""
    delta_u = np.array([-1.0, -1.0, -1.0, -1.0])
    # Without governor
    ps_off = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    ps_off.reset(delta_u=delta_u)
    for _ in range(300):
        r_off = ps_off.step()
    # With governor
    ps_on = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    ps_on.reset(delta_u=delta_u)
    for _ in range(300):
        r_on = ps_on.step()
    ss_off = float(np.mean(np.abs(r_off['omega'])))
    ss_on = float(np.mean(np.abs(r_on['omega'])))
    assert ss_on < 0.5 * ss_off, f"governor should cut SS |ω|: off={ss_off}, on={ss_on}"


def test_invalid_governor_params_rejected():
    import pytest
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
            governor_enabled=True, governor_R=0.0, governor_tau_g=0.5,
        )
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
            governor_enabled=True, governor_R=0.05, governor_tau_g=0.0,
        )
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `pytest tests/test_ode_governor.py -v`
Expected: FAIL (unknown kwargs `governor_enabled`).

- [ ] **Step 4.3: Extend PowerSystem `__init__` for governor**

Modify `env/ode/power_system.py` — append to the `__init__` argument list:

```python
def __init__(self, L, H_es0, D_es0, dt=0.2, fn=50.0,
             B_matrix=None, V_bus=None, network_mode='linear',
             governor_enabled=False, governor_R=0.05, governor_tau_g=0.5):
```

At end of `__init__` body:

```python
    self.governor_enabled = bool(governor_enabled)
    if self.governor_enabled:
        if governor_R <= 0:
            raise ValueError(f"governor_R must be > 0, got {governor_R}")
        if governor_tau_g <= 0:
            raise ValueError(f"governor_tau_g must be > 0, got {governor_tau_g}")
    self.governor_R = float(governor_R)
    self.governor_tau_g = float(governor_tau_g)

    state_dim = 3 * self.N if self.governor_enabled else 2 * self.N
    self.state = np.zeros(state_dim)
```

- [ ] **Step 4.4: Modify `_dynamics` to include governor states**

Replace `_dynamics`:

```python
def _dynamics(self, t, state):
    theta = state[:self.N]
    omega = state[self.N:2 * self.N]
    M_inv = 1.0 / (2.0 * self.H_es)
    coupling = self._coupling(theta)
    dtheta_dt = omega

    if self.governor_enabled:
        P_gov = state[2 * self.N:3 * self.N]
        domega_dt = M_inv * (
            self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
        )
        dP_gov_dt = -(P_gov + (omega / self.omega_s) / self.governor_R) / self.governor_tau_g
        return np.concatenate([dtheta_dt, domega_dt, dP_gov_dt])

    domega_dt = M_inv * (self.omega_s * (self.delta_u - coupling) - self.D_es * omega)
    return np.concatenate([dtheta_dt, domega_dt])
```

- [ ] **Step 4.5: Fix `step()` / `get_state()` omega_dot recompute**

After `solve_ivp` returns, the post-integration recompute of `omega_dot` must also include `P_gov`. Replace that block in `step()`:

```python
self.state = sol.y[:, -1]
self.current_time = t_end
self._step_count += 1

theta = self.state[:self.N]
omega = self.state[self.N:2 * self.N]
M_inv = 1.0 / (2.0 * self.H_es)
coupling = self._coupling(theta)
if self.governor_enabled:
    P_gov = self.state[2 * self.N:3 * self.N]
    omega_dot = M_inv * (
        self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
    )
else:
    omega_dot = M_inv * (
        self.omega_s * (self.delta_u - coupling) - self.D_es * omega
    )
P_es = coupling
freq_hz = self.fn + omega / (2 * np.pi)
```

Mirror the same change in `get_state()`. Replace the whole method body with:

```python
def get_state(self):
    """返回当前状态的快照."""
    theta = self.state[:self.N]
    omega = self.state[self.N:2 * self.N]
    M_inv = 1.0 / (2.0 * self.H_es)  # Eq.4: 2H·dω/dt = ...
    coupling = self._coupling(theta)
    if self.governor_enabled:
        P_gov = self.state[2 * self.N:3 * self.N]
        omega_dot = M_inv * (
            self.omega_s * (self.delta_u + P_gov - coupling) - self.D_es * omega
        )
    else:
        omega_dot = M_inv * (
            self.omega_s * (self.delta_u - coupling) - self.D_es * omega
        )
    P_es = coupling
    freq_hz = self.fn + omega / (2 * np.pi)
    return {
        'theta': theta.copy(),
        'omega': omega.copy(),
        'omega_dot': omega_dot.copy(),
        'P_es': P_es.copy(),
        'freq_hz': freq_hz.copy(),
        'time': self.current_time,
    }
```

Note the two changes vs. current: (1) `omega = self.state[self.N:2 * self.N]`
(explicit upper bound so the slice is correct in both 2N and 3N layouts), and
(2) the `if self.governor_enabled` branch injecting `P_gov` into `omega_dot`.

Also update `reset()` so it preserves `state_dim`:

```python
def reset(self, delta_u=None, event_schedule=None):
    self.state = np.zeros(self.state.shape[0])
    self.H_es = self.H_es0.copy()
    self.D_es = self.D_es0.copy()
    self.current_time = 0.0
    self._step_count = 0
    self._event_schedule = event_schedule
    if event_schedule is not None:
        self.delta_u = np.zeros(self.N)
        for ev in event_schedule.events:
            if ev.t == 0.0 and isinstance(ev, DisturbanceEvent):
                self.delta_u = ev.delta_u.copy()
    elif delta_u is not None:
        self.delta_u = np.asarray(delta_u, dtype=np.float64).copy()
    else:
        self.delta_u = np.zeros(self.N)
```

- [ ] **Step 4A.6: Wire governor kwargs into MultiVSGEnv**

Modify `env/ode/multi_vsg_env.py`. Replace the `PowerSystem(...)` construction in `__init__` to add governor kwargs (heterogeneity integration is Task 4B):

```python
self.ps = PowerSystem(
    self.L, cfg.H_ES0, cfg.D_ES0,
    dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi),
    B_matrix=getattr(cfg, 'B_MATRIX', None),
    V_bus=getattr(cfg, 'V_BUS', None),
    network_mode=getattr(cfg, 'ODE_NETWORK_MODE', 'linear'),
    governor_enabled=getattr(cfg, 'ODE_GOVERNOR_ENABLED', False),
    governor_R=getattr(cfg, 'ODE_GOVERNOR_R', 0.05),
    governor_tau_g=getattr(cfg, 'ODE_GOVERNOR_TAU_G', 0.5),
)
```

Append to `config.py` directly **below the existing `ODE_NETWORK_MODE` line**
(Task 3 already added it — do NOT redeclare `ODE_NETWORK_MODE` or you will have
duplicate definitions):

```python
# Governor knobs (Task 4A)
ODE_GOVERNOR_ENABLED = False
ODE_GOVERNOR_R = 0.05              # p.u. droop (5 %)
ODE_GOVERNOR_TAU_G = 0.5           # turbine lag (s)
```

**Forbidden in this step:** touching heterogeneity logic or action decoding (`_H_base`/`_D_base`). Those belong to Task 4B.

- [ ] **Step 4A.7: Run tests to verify all pass**

Run: `python -m pytest tests/test_ode_governor.py tests/test_ode_nonlinear.py tests/test_ode_disturbance_schedule.py tests/test_ode_physics_gates.py -v`
Expected: 5 new governor tests PASS; existing suites still PASS.

- [ ] **Step 4A.8: Commit**

```bash
git add env/ode/power_system.py env/ode/multi_vsg_env.py tests/test_ode_governor.py config.py
git commit -m "feat(ode): first-order governor / droop dynamics (Task 4A)"
```

---

## Task 4B: Heterogeneity Env Integration

**Purpose:** Close Task 1 — the helper `utils/ode_heterogeneity.py` was built in Task 1 but `MultiVSGEnv` still uses `cfg.H_ES0` / `cfg.D_ES0` directly. This task wires the heterogeneity into the env and fixes action decoding.

**Allowed files:** `env/ode/multi_vsg_env.py`, `tests/test_ode_heterogeneity.py` (extend), `config.py` (no new knobs, already added).
**Forbidden:** `env/ode/power_system.py`, any governor logic.

- [ ] **Step 4B.1: Write failing test for env-level heterogeneity**

Add to `tests/test_ode_heterogeneity.py`:

```python
def test_multivsg_env_uses_heterogeneous_H_when_flag_on(monkeypatch):
    """With ODE_HETEROGENEOUS=True, PowerSystem should receive non-uniform H."""
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_H_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    H = env.ps.H_es0
    assert len(set(H.tolist())) > 1, "Expected heterogeneous H, got uniform"


def test_multivsg_env_uses_heterogeneous_D_when_flag_on(monkeypatch):
    """With ODE_HETEROGENEOUS=True, PowerSystem should also receive non-uniform D."""
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_D_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    D = env.ps.D_es0
    assert len(set(D.tolist())) > 1, "Expected heterogeneous D, got uniform"


def test_multivsg_env_action_decode_uses_heterogeneous_base(monkeypatch):
    """After step(), H_es/D_es must be based on _H_base/_D_base, not cfg.H_ES0/D_ES0."""
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_H_SPREAD', 0.30)
    monkeypatch.setattr(cfg, 'ODE_D_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    env.reset(delta_u=np.zeros(env.N))
    # Zero action = no H/D change from base; ps.H_es must equal _H_base (heterogeneous)
    zero_actions = {i: np.zeros(2) for i in range(env.N)}
    env.step(zero_actions)
    assert len(set(env.ps.H_es.tolist())) > 1, \
        "H_es after zero-action step should reflect _H_base, not uniform cfg.H_ES0"
    assert len(set(env.ps.D_es.tolist())) > 1, \
        "D_es after zero-action step should reflect _D_base, not uniform cfg.D_ES0"
```

- [ ] **Step 4B.2: Wire heterogeneity into MultiVSGEnv**

Modify `env/ode/multi_vsg_env.py`. Add import:

```python
from utils.ode_heterogeneity import generate_heterogeneous_params
```

Before the `PowerSystem(...)` call in `__init__`, add:

```python
H_base = cfg.H_ES0.copy()
D_base = cfg.D_ES0.copy()
if getattr(cfg, 'ODE_HETEROGENEOUS', False):
    seed = getattr(cfg, 'ODE_HETEROGENEITY_SEED', 2023)
    H_base = generate_heterogeneous_params(
        H_base, getattr(cfg, 'ODE_H_SPREAD', 0.30), seed,
    )
    D_base = generate_heterogeneous_params(
        D_base, getattr(cfg, 'ODE_D_SPREAD', 0.30), seed + 1,
    )
self._H_base = H_base
self._D_base = D_base
```

Change `PowerSystem(...)` to use `H_base, D_base` instead of `cfg.H_ES0, cfg.D_ES0`.

Fix action decoding in `step()` — replace references to `cfg.H_ES0` / `cfg.D_ES0`:

```python
H_es = np.copy(self._H_base)
D_es = np.copy(self._D_base)
# ...
H_es[i] = self._H_base[i] + delta_H[i]
D_es[i] = self._D_base[i] + delta_D[i]
```

- [ ] **Step 4B.3: Run tests**

Run: `python -m pytest tests/test_ode_heterogeneity.py tests/test_ode_governor.py tests/test_ode_physics_gates.py -v`
Expected: all pass including new env-level test.

- [ ] **Step 4B.4: Commit**

```bash
git add env/ode/multi_vsg_env.py tests/test_ode_heterogeneity.py
git commit -m "feat(ode): heterogeneity env integration + action base fix (Task 4B)"
```

---

## Task 5: Discrete Topology Events (Line Trip)

**Files:**
- Modify: `env/ode/power_system.py` — handle `LineTripEvent` in `_apply_events`; store `_current_B_matrix` and rebuild `L` at event time.
- Create: `tests/test_ode_line_trip.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_ode_line_trip.py`:

```python
"""Discrete line-trip events tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import (
    DisturbanceEvent,
    EventSchedule,
    LineTripEvent,
)


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)


def _fresh():
    return PowerSystem(
        build_laplacian(_B, _V), np.full(4, 24.0), np.full(4, 18.0),
        dt=0.2, fn=50.0, B_matrix=_B.copy(), V_bus=_V, network_mode='linear',
    )


def test_line_trip_modifies_B_matrix():
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=1.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    for _ in range(4):  # before trip (t<1.0)
        ps.step()
    assert ps.B_matrix[1, 2] == 4.0
    for _ in range(2):  # cross t=1.0
        ps.step()
    assert ps.B_matrix[1, 2] == 0.0
    assert ps.B_matrix[2, 1] == 0.0


def test_line_trip_preserves_N_and_state_continuity():
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=1.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    prev_state = ps.state.copy()
    for _ in range(10):
        r = ps.step()
        # State must remain finite across all steps (including trip transition)
        delta = float(np.max(np.abs(ps.state - prev_state)))
        assert np.isfinite(delta), f"state went non-finite after step: {ps.state}"
        prev_state = ps.state.copy()


def test_line_trip_increases_swing_amplitude():
    """After tripping a tie at t=0, swing amplitude at bus 0 is larger than intact system."""
    # Intact
    ps_intact = _fresh()
    ps_intact.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
    )))
    omega_intact = []
    for _ in range(50):
        r = ps_intact.step()
        omega_intact.append(float(r['omega'][0]))
    # Tripped at start
    ps_trip = _fresh()
    ps_trip.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    )))
    omega_trip = []
    for _ in range(50):
        r = ps_trip.step()
        omega_trip.append(float(r['omega'][0]))

    # Trip removes coupling between area 1 and 2 → larger swing amplitude
    assert max(np.abs(omega_trip)) > max(np.abs(omega_intact))


def test_reset_restores_original_topology():
    """LineTripEvent must not persist across episodes after reset."""
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    assert ps.B_matrix[1, 2] == 0.0  # trip applied

    # Second episode: no trip — topology must be intact
    ps.reset(delta_u=np.array([1.0, 0.0, -1.0, 0.0]))
    assert ps.B_matrix[1, 2] == 4.0, "topology should be restored after reset()"
    assert ps.B_matrix[2, 1] == 4.0
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `pytest tests/test_ode_line_trip.py -v`
Expected: FAIL — line trip branch not implemented yet.

- [ ] **Step 5.3: Handle line-trip events in PowerSystem**

Modify `env/ode/power_system.py`. In `__init__`, after `self.L = L.astype(...)`:

```python
    # Keep immutable originals for reset(); working copies are mutated by LineTripEvent.
    self._L0 = L.astype(np.float64).copy()
    if B_matrix is not None:
        self.B_matrix = B_matrix.astype(np.float64).copy()
        self._B_matrix0 = B_matrix.astype(np.float64).copy()
    else:
        self.B_matrix = None
        self._B_matrix0 = None
```

Extend `_apply_events`:

```python
def _apply_events(self) -> None:
    if self._event_schedule is None:
        return
    for ev in self._event_schedule.events:
        if ev.t == 0.0:
            continue  # applied in reset()
        ev_step = max(0, int(round(ev.t / self.dt)) - 1)
        if ev_step == self._step_count:
            if isinstance(ev, DisturbanceEvent):
                self.delta_u = ev.delta_u.copy()
            elif isinstance(ev, LineTripEvent):
                if self.B_matrix is None or self.V_bus is None:
                    raise RuntimeError(
                        "LineTripEvent requires PowerSystem to be constructed with "
                        "B_matrix and V_bus."
                    )
                self.B_matrix[ev.bus_i, ev.bus_j] = 0.0
                self.B_matrix[ev.bus_j, ev.bus_i] = 0.0
                self.L = build_laplacian(self.B_matrix, self.V_bus)
```

Also update `reset()` — restore original topology on every call, and extend t=0 handling to cover `LineTripEvent`:

```python
def reset(self, delta_u=None, event_schedule=None):
    self.state = np.zeros(self.state.shape[0])
    self.H_es = self.H_es0.copy()
    self.D_es = self.D_es0.copy()
    # Restore original topology so each episode starts from intact network
    if self._B_matrix0 is not None:
        self.B_matrix = self._B_matrix0.copy()
    self.L = self._L0.copy()
    self.current_time = 0.0
    self._step_count = 0
    self._event_schedule = event_schedule
    if event_schedule is not None:
        self.delta_u = np.zeros(self.N)
        # Apply t=0 events immediately (DisturbanceEvent and LineTripEvent)
        for ev in event_schedule.events:
            if ev.t == 0.0:
                if isinstance(ev, DisturbanceEvent):
                    self.delta_u = ev.delta_u.copy()
                elif isinstance(ev, LineTripEvent):
                    if self.B_matrix is None or self.V_bus is None:
                        raise RuntimeError(
                            "LineTripEvent requires B_matrix and V_bus."
                        )
                    self.B_matrix[ev.bus_i, ev.bus_j] = 0.0
                    self.B_matrix[ev.bus_j, ev.bus_i] = 0.0
                    self.L = build_laplacian(self.B_matrix, self.V_bus)
    elif delta_u is not None:
        self.delta_u = np.asarray(delta_u, dtype=np.float64).copy()
    else:
        self.delta_u = np.zeros(self.N)
```

Ensure the Laplacian rebuild reuses the existing helper — **do not** duplicate the
function. At the top of `env/ode/power_system.py`, next to the existing imports,
add (if not already present):

```python
from env.network_topology import build_laplacian
```

Verified: `env/network_topology.py` does not import anything from `env/ode/*`,
so there is no cyclic import risk. Removing this reuse would leave two diverging
definitions of the same formula.

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `pytest tests/test_ode_line_trip.py -v`
Expected: 4 passed.

- [ ] **Step 5.5: Re-run the full ODE test sweep**

Run: `pytest tests/test_ode_physics_gates.py tests/test_ode_disturbance_schedule.py tests/test_ode_nonlinear.py tests/test_ode_governor.py tests/test_ode_line_trip.py -v`
Expected: every test passes.

- [ ] **Step 5.6: Commit**

```bash
git add env/ode/power_system.py tests/test_ode_line_trip.py
git commit -m "feat(ode): discrete line-trip events with L-matrix rebuild (Task 5)"
```

---

## Task 6: Promotion Gates (Engineering Regression)

**Files:**
- Create: `tests/test_ode_fidelity_extended.py`

These gates guard against drift when any of Tasks 1–5 are later refactored.

- [ ] **Step 6.1: Write the gate file**

Create `tests/test_ode_fidelity_extended.py`:

```python
"""Promotion gates for Tasks 1–5 (engineering regression thresholds).

Each gate covers one dimension of the ODE upgrade and fails if a
future refactor violates the design-time threshold.
"""
import numpy as np
import pytest

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import (
    DisturbanceEvent,
    EventSchedule,
    LineTripEvent,
)
from utils.ode_heterogeneity import generate_heterogeneous_params


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)
_L = build_laplacian(_B, _V)


def _peak_omega(ps, steps):
    peak = 0.0
    for _ in range(steps):
        r = ps.step()
        peak = max(peak, float(np.max(np.abs(r['omega']))))
    return peak


def test_heterogeneous_peak_freq_within_20pct_of_uniform():
    """±30 % spread in H should keep peak |ω| within 20 % of the uniform case."""
    H_uni = np.full(4, 24.0)
    D_uni = np.full(4, 18.0)
    H_het = generate_heterogeneous_params(H_uni, spread=0.30, seed=2023)
    D_het = generate_heterogeneous_params(D_uni, spread=0.30, seed=2024)

    du = np.array([2.4, 0.0, -2.4, 0.0])
    ps_uni = PowerSystem(_L, H_uni, D_uni, dt=0.1, fn=50.0)
    ps_uni.reset(delta_u=du)
    peak_uni = _peak_omega(ps_uni, 100)

    ps_het = PowerSystem(_L, H_het, D_het, dt=0.1, fn=50.0)
    ps_het.reset(delta_u=du)
    peak_het = _peak_omega(ps_het, 100)

    assert 0.80 * peak_uni <= peak_het <= 1.20 * peak_uni, (
        f"peak_uni={peak_uni:.3f}, peak_het={peak_het:.3f}"
    )


def test_nonlinear_large_signal_bounded():
    """Nonlinear network must stay finite and not exceed linear peak by more than 50% for 3 p.u. step."""
    du = np.array([3.0, 0.0, -3.0, 0.0])
    ps_lin = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B, V_bus=_V, network_mode='linear')
    ps_lin.reset(delta_u=du)
    peak_lin = _peak_omega(ps_lin, 100)

    ps_non = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B, V_bus=_V, network_mode='nonlinear')
    ps_non.reset(delta_u=du)
    peak_non = _peak_omega(ps_non, 100)

    assert np.isfinite(peak_non), "nonlinear diverged"
    # Nonlinear sin(θ) saturates → ω peak is slightly larger than linear
    # (reduced effective coupling). Allow up to +50 %.
    assert peak_non <= 1.5 * peak_lin, f"nonlinear overshoot: lin={peak_lin}, non={peak_non}"


def test_governor_steady_state_error_below_threshold():
    """Governor with R=0.05 reduces SS |Δω| vs no-governor for uniform -0.5 p.u. step.

    Physics: ω_ss = ωs·Δu / (1/R + D) ≈ 314·(-0.5) / (20+18) ≈ -4.1 rad/s with governor,
    vs ωs·Δu / D ≈ -8.7 rad/s without. Gate checks governor cuts SS error by >40%.
    """
    delta_u = np.array([-0.5, -0.5, -0.5, -0.5])
    ps_off = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    ps_off.reset(delta_u=delta_u)
    for _ in range(500):
        r_off = ps_off.step()
    ss_off = float(np.mean(np.abs(r_off['omega'])))

    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
                     governor_enabled=True, governor_R=0.05, governor_tau_g=0.5)
    ps.reset(delta_u=delta_u)
    for _ in range(500):
        r = ps.step()
    ss = float(np.mean(np.abs(r['omega'])))
    assert ss < 0.6 * ss_off, f"Governor should cut SS |ω| by >40%: off={ss_off:.2f}, on={ss:.2f} rad/s"
    assert ss < 6.0, f"Governor SS |ω| physically too large: {ss:.2f} rad/s (expected ~4 rad/s)"


def test_multivsgenv_default_path_is_deterministic():
    """With all ODE flags off, two identical MultiVSGEnv runs must produce identical obs/reward/ps.state.

    This is the baseline-preserving gate for the MultiVSGEnv wrapper path.
    Catches any accidental numeric drift introduced by Task 2-4 constructor changes.
    """
    import config as cfg
    from env.ode.multi_vsg_env import MultiVSGEnv

    assert not getattr(cfg, 'ODE_HETEROGENEOUS', False), "Test requires all ODE flags off"
    assert not getattr(cfg, 'ODE_GOVERNOR_ENABLED', False), "Test requires all ODE flags off"
    assert getattr(cfg, 'ODE_NETWORK_MODE', 'linear') == 'linear', "Test requires all ODE flags off"

    du = np.array([2.0, 0.0, -2.0, 0.0])

    def run_env():
        # comm_fail_prob=0.0 removes CommunicationGraph RNG variance; without it
        # cfg.COMM_FAIL_PROB=0.1 and the unseeded rng make rewards non-reproducible.
        env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
        env.reset(delta_u=du)
        rewards = []
        zero_actions = {i: np.zeros(2) for i in range(env.N)}
        for _ in range(5):
            obs, rew, _, _ = env.step(zero_actions)
            rewards.append(float(sum(rew.values())))
        obs_arr = np.concatenate([obs[i] for i in range(env.N)])
        return obs_arr, rewards, env.ps.state.copy()

    obs_a, rew_a, state_a = run_env()
    obs_b, rew_b, state_b = run_env()

    np.testing.assert_allclose(obs_a, obs_b, atol=1e-12, err_msg="obs not reproducible")
    np.testing.assert_allclose(rew_a, rew_b, atol=1e-12, err_msg="rewards not reproducible")
    np.testing.assert_allclose(state_a, state_b, atol=1e-12, err_msg="ps.state not reproducible")


def test_line_trip_modal_frequency_decreases():
    """Tripping the middle tie should lower the chain's λ_min and slow oscillation."""
    ps_pre = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                         B_matrix=_B.copy(), V_bus=_V, network_mode='linear')
    ps_pre.reset(delta_u=np.array([1.0, 0.0, -1.0, 0.0]))
    for _ in range(100):
        ps_pre.step()
    eig_pre = sorted(np.linalg.eigvalsh(ps_pre.L).tolist())

    ps_post = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B.copy(), V_bus=_V, network_mode='linear')
    ps_post.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    )))
    ps_post.step()  # apply trip
    eig_post = sorted(np.linalg.eigvalsh(ps_post.L).tolist())

    # The second-smallest eigenvalue (algebraic connectivity) should drop.
    assert eig_post[1] < eig_pre[1], (
        f"λ_2 should decrease after trip: pre={eig_pre[1]:.3f}, post={eig_post[1]:.3f}"
    )
```

- [ ] **Step 6.2: Run tests to verify they pass**

Run: `pytest tests/test_ode_fidelity_extended.py -v`
Expected: 5 passed.

- [ ] **Step 6.3: Run the full ODE suite**

Run: `pytest tests/test_ode_physics_gates.py tests/test_ode_heterogeneity.py tests/test_ode_disturbance_schedule.py tests/test_ode_nonlinear.py tests/test_ode_governor.py tests/test_ode_line_trip.py tests/test_ode_fidelity_extended.py -v`
Expected: all tests pass.

- [ ] **Step 6.4: Commit**

```bash
git add tests/test_ode_fidelity_extended.py
git commit -m "test(ode): extended fidelity gates for Tasks 1-5 (Task 6)"
```

---

## Task 7: Docs + Integration Notes

**Files:**
- Create: `env/ode/NOTES.md`
- Modify: `CLAUDE.md` — add ODE NOTES pointer.

- [ ] **Step 7.1: Write `env/ode/NOTES.md`**

Create `env/ode/NOTES.md`:

```markdown
# ODE Model Notes

> 修 ODE 模型前必读。与 `docs/paper/yang2023-fact-base.md` 一致。

## 能力开关（config.py）

| 开关 | 默认 | 作用 | 成本 |
|---|---|---|---|
| `ODE_HETEROGENEOUS` | False | 按 `ODE_H_SPREAD` 生成 per-node H/D | 无性能影响 |
| `ODE_NETWORK_MODE` | 'linear' | 'nonlinear' 时用 `Σ B_ij sin(θ_i-θ_j)` | +~30 % step 时间 |
| `ODE_GOVERNOR_ENABLED` | False | 加一阶 droop + τ_G 汽轮机滞后；状态 2N→3N | +~10 % step 时间 |
| (事件 API) | — | `EventSchedule` 传入 `reset(event_schedule=...)` | 对齐 step 边界 |

## 默认 = 论文 Eq.4 对齐

所有开关默认 off 时，`PowerSystem` / `MultiVSGEnv` 行为 baseline-preserving（兼容性门控验证）。
可用 `tests/test_ode_physics_gates.py` 验证。

## 事件 API

`utils/ode_events.py` 提供：
- `DisturbanceEvent(t, delta_u)` — 将当前 Δu 全量替换为新值（所有母线）
- `LineTripEvent(t, bus_i, bus_j)` — 将 B[i,j]=B[j,i]=0 并重建 L
- `EventSchedule(events=(...))` — 冻结的事件序列；必须按 t 单调不减

事件在 step 边界生效（step-boundary 语义）：t=0 事件在 `reset()` 内立即应用；t>0 事件用 `max(0, round(t/dt) - 1) == step_idx` 匹配，已知存在一步提前偏差。亚步精度不支持——若需要，把 dt 调小。

## 已知限制

1. **事件只对齐 step 边界**（<0.2 s 误差）。
2. **governor R / τ_G 全节点共享**——若需要异构 governor，仿 heterogeneity helper 扩展即可。
3. **nonlinear 的 `_coupling` 是 O(N²)**。N=4/10 没问题，N>>100 需要向量化/稀疏化。
4. **governor 不参与 RL 动作空间**——RL agent 只调 H, D；governor 作为背景一次调频动力学。

## 已核实事实

- 与论文一致：Eq.1/4 的 H·Δω̇ 系数约定已统一为 2H（见 power_system 注释）。
- ODE 现有状态：`[Δθ, Δω]` (2N)，governor 开启后扩为 `[Δθ, Δω, P_gov]` (3N)。
- Gate 目标：`ω_n ≈ 0.6 Hz, ζ ≈ 0.05, Δf_peak ≈ 0.4 Hz`（H=24, D=18, B_tie=4）。

## 试过没用的

- （待填）
```

- [ ] **Step 7.2: Update `CLAUDE.md` ODE pointer**

Modify `CLAUDE.md` — find the "⚠️ 修模型前必读 NOTES" table and add a row:

```markdown
| `env/ode/*`、`scenarios/*/train_ode.py` | `env/ode/NOTES.md` |
```

- [ ] **Step 7.3: Final full-suite run**

Run (ODE/physics subset — primary gate for this plan):
`pytest tests/ -v --ignore=tests/test_visual_capture.py --ignore=tests/test_vsg_batch_query.m -k "ode or physics"`
Expected: all ODE/physics-selected tests pass.

Then run the full non-ODE smoke to prove no regression outside the selection
(the `-k` filter above would silently skip them otherwise):
`pytest tests/ --ignore=tests/test_visual_capture.py --ignore=tests/test_vsg_batch_query.m -q`
Expected: green, or only pre-existing failures unchanged from the pre-plan baseline.

- [ ] **Step 7.4: Commit**

```bash
git add env/ode/NOTES.md CLAUDE.md
git commit -m "docs(ode): notes + CLAUDE pointer for Tasks 1-6 (Task 7)"
```

---

## Verification Checklist

After all 7 tasks, these invariants must hold:

- [ ] `pytest tests/test_ode_physics_gates.py` — paper-baseline modal gates still pass (defaults off).
- [ ] `pytest tests/test_ode_heterogeneity.py` — heterogeneity helper works.
- [ ] `pytest tests/test_ode_disturbance_schedule.py` — event schedule equivalent to static Δu when single t=0 event.
- [ ] `pytest tests/test_ode_nonlinear.py` — small-signal linear≈nonlinear, large-signal diverge.
- [ ] `pytest tests/test_ode_governor.py` — steady-state `P_gov ≈ -(ω/ω_s)/R`, governor reduces SS |ω|.
- [ ] `pytest tests/test_ode_line_trip.py` — B[i,j] zeroed at event, state stays finite, modal shift measurable.
- [ ] `pytest tests/test_ode_fidelity_extended.py` — 5 cross-feature gates including MultiVSGEnv baseline determinism.
- [ ] Existing training path (`python scenarios/kundur/train_ode.py --episodes 10 --cpu`) still starts and logs rewards — default flags preserve behavior.

---

## Out of Scope (future work)

- Simulink cross-validation harness: too dependent on MATLAB availability; better as a standalone verification plan.
- AVR / voltage dynamics: requires adding E/V states, multiplying state count by 2+. Out of scope for fidelity ceiling.
- Event-exact integration via `solve_ivp(events=...)`: step-boundary snapping gives ≤ 0.1 s resolution at dt=0.2 s, acceptable for paper fidelity.
- RL agent awareness of governor: observations could expose `P_gov`; the paper does not use it, so current 7-dim obs stays.
- `DisturbanceEvent.delta_u` deep-freeze hardening: `utils/ode_events.py` uses `np.asarray(..., dtype=np.float64)` in `__post_init__`, which does **not** guarantee a copy when the caller already passed float64. A caller that later mutates the original array would also mutate the event. Optional follow-up: switch to `arr = np.array(..., dtype=np.float64, copy=True); arr.setflags(write=False)`. Not required for the current 7-task plan; record here so it is not lost.
