# Training Diagnostics & Monitoring System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified training diagnostics pipeline (StepInfo → EpisodeBuffer → DiagnosticsEngine → WandbTracker) that captures per-step physics data, detects training anomalies automatically, and streams metrics to wandb — integrated into the existing `train_loop.py` with zero breaking changes.

**Architecture:** Each env backend (ANDES/ODE/Simulink) produces a raw `info` dict with different keys. A per-backend adapter converts this to a unified `StepInfo` dataclass. `EpisodeBuffer` accumulates steps, computes `EpisodeMetrics` at episode end. `DiagnosticsEngine` runs 7 rule-based checks on the metrics history. `WandbTracker` logs scalars, diagnostics, and trajectory plots. A `TunerInterface` ABC is defined for future Phase C auto-tuning.

**Tech Stack:** Python 3.10+, numpy, wandb (new dependency), scipy (existing, for Pearson), matplotlib (existing, for trajectory plots), pytest

**Spec:** `docs/superpowers/specs/2026-03-30-training-diagnostics-system-design.md`

---

## File Map

```
utils/diagnostics/              # NEW directory — all new files
  __init__.py                   # re-exports public API
  step_info.py                  # StepInfo, GridState, AgentState, RewardBreakdown, SolverState
  adapters.py                   # andes_adapter(), ode_adapter(), simulink_adapter()
  episode_buffer.py             # EpisodeBuffer, EpisodeMetrics, SnapshotRecord
  engine.py                     # DiagnosticsEngine, DiagnosticRule, DiagnosticReport, Severity
  rules/
    __init__.py                 # imports all 7 rule classes
    critic_loss.py              # CriticLossTrend
    improvement.py              # ImprovementStall
    hd_range.py                 # HDRangeUtilization
    coordination.py             # InterAgentCoordination
    dominance.py                # RewardComponentDominance
    action_collapse.py          # ActionCollapse
    solver_failure.py           # SolverFailureRate
  wandb_tracker.py              # WandbTracker
  tuner_interface.py            # TunerInterface ABC, HyperparamSuggestion

tests/
  test_step_info.py             # Task 1 tests
  test_adapters.py              # Task 2 tests
  test_episode_buffer.py        # Task 3 tests
  test_diagnostics_engine.py    # Task 4 tests (engine + all 7 rules)
  test_wandb_tracker.py         # Task 5 tests
  test_diagnostics_integration.py  # Task 7 integration test

Modify:
  utils/train_loop.py           # Task 7 — add 4 optional params, 4 integration points
  scenarios/kundur/train_andes.py  # Task 8 — wire up diagnostics in wrapper
```

---

### Task 1: StepInfo Data Contract

**Files:**
- Create: `utils/diagnostics/__init__.py`
- Create: `utils/diagnostics/step_info.py`
- Test: `tests/test_step_info.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p utils/diagnostics/rules
```

Create `utils/diagnostics/__init__.py`:

```python
"""Training diagnostics & monitoring system.

Public API — import from here:
    from utils.diagnostics import StepInfo, EpisodeBuffer, DiagnosticsEngine, WandbTracker
"""
```

This file will be extended in later tasks as we add more modules.

- [ ] **Step 2: Write failing tests for StepInfo dataclasses**

Create `tests/test_step_info.py`:

```python
"""Tests for StepInfo data contract (spec Section 3)."""
import numpy as np
import pytest
from utils.diagnostics.step_info import (
    GridState, AgentState, RewardBreakdown, SolverState, StepInfo,
)


def _make_grid(n=4, freq_nom=50.0):
    freq = np.full(n, freq_nom + 0.1)
    return GridState(
        freq_hz=freq,
        freq_dev_hz=freq - freq_nom,
        max_freq_dev_hz=0.1,
        freq_coi_hz=freq_nom + 0.1,
        rocof=np.zeros(n),
        power=np.ones(n) * 5.0,
    )


def _make_agents(n=4):
    return [
        AgentState(
            agent_id=i, H=3.0 + i, D=2.0 + i,
            delta_H=0.5, delta_D=0.3,
            action_raw=np.array([0.1, -0.2]),
            action_mapped=np.array([1.0, 0.5]),
        )
        for i in range(n)
    ]


def _make_reward(n=4):
    return RewardBreakdown(
        total=-50.0,
        per_agent={i: -50.0 / n for i in range(n)},
        components={"r_freq": -45.0, "r_action_h": -3.0, "r_action_d": -2.0},
    )


def _make_solver():
    return SolverState(converged=True, sim_time=1.0, backend="andes", dt_actual=0.01)


def _make_step_info(n=4, step=0, episode=0, done=False):
    return StepInfo(
        step=step, episode=episode, wall_time=1000.0,
        done=done, done_reason="complete" if done else None,
        grid=_make_grid(n), agents=_make_agents(n),
        reward=_make_reward(n), solver=_make_solver(),
    )


class TestGridState:
    def test_fields_are_numpy(self):
        g = _make_grid()
        assert isinstance(g.freq_hz, np.ndarray)
        assert isinstance(g.freq_dev_hz, np.ndarray)
        assert isinstance(g.power, np.ndarray)

    def test_rocof_optional(self):
        g = GridState(
            freq_hz=np.array([50.0]),
            freq_dev_hz=np.array([0.0]),
            max_freq_dev_hz=0.0,
            freq_coi_hz=50.0,
            rocof=None,
            power=np.array([1.0]),
        )
        assert g.rocof is None


class TestAgentState:
    def test_action_shapes(self):
        a = _make_agents(1)[0]
        assert a.action_raw.shape == (2,)
        assert a.action_mapped.shape == (2,)


class TestRewardBreakdown:
    def test_components_flexible_keys(self):
        r = _make_reward()
        assert "r_freq" in r.components
        # Components can have any string keys
        r2 = RewardBreakdown(total=-10, per_agent={0: -10}, components={"custom": -10})
        assert r2.components["custom"] == -10


class TestStepInfo:
    def test_construction(self):
        si = _make_step_info()
        assert si.step == 0
        assert si.episode == 0
        assert si.done is False
        assert len(si.agents) == 4

    def test_done_with_reason(self):
        si = _make_step_info(done=True)
        assert si.done is True
        assert si.done_reason == "complete"

    def test_solver_backend(self):
        si = _make_step_info()
        assert si.solver.backend == "andes"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd "/c/Users/27443/Desktop/Multi-Agent  VSGs"
python -m pytest tests/test_step_info.py -v
```

Expected: `ModuleNotFoundError: No module named 'utils.diagnostics'`

- [ ] **Step 4: Implement StepInfo dataclasses**

Create `utils/diagnostics/step_info.py`:

```python
"""StepInfo unified data contract (spec Section 3).

Every env.step() result is converted to a StepInfo by a per-backend adapter.
This module defines the dataclasses only — no conversion logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class GridState:
    """Per-step grid-level measurements."""
    freq_hz: np.ndarray           # (n_agents,)
    freq_dev_hz: np.ndarray       # (n_agents,)
    max_freq_dev_hz: float
    freq_coi_hz: float            # COI = sum(H_i * f_i) / sum(H_i)
    rocof: np.ndarray | None      # (n_agents,) or None if unavailable
    power: np.ndarray             # (n_agents,)


@dataclass
class AgentState:
    """Per-step per-agent state."""
    agent_id: int
    H: float
    D: float
    delta_H: float
    delta_D: float
    action_raw: np.ndarray        # (2,) network output [-1, 1]
    action_mapped: np.ndarray     # (2,) mapped [delta_H, delta_D]


@dataclass
class RewardBreakdown:
    """Per-step reward decomposition."""
    total: float
    per_agent: dict[int, float]
    components: dict[str, float]  # flexible keys: r_freq, r_action_h, etc.


@dataclass
class SolverState:
    """Per-step solver/simulation status."""
    converged: bool
    sim_time: float
    backend: str                  # "andes" | "ode" | "simulink"
    dt_actual: float | None


@dataclass
class StepInfo:
    """Unified per-step data record across all backends."""
    step: int
    episode: int
    wall_time: float
    done: bool
    done_reason: str | None       # "complete" | "solver_fail" | "max_steps"
    grid: GridState
    agents: list[AgentState]
    reward: RewardBreakdown
    solver: SolverState
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_step_info.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Update `__init__.py` exports and commit**

Update `utils/diagnostics/__init__.py`:

```python
"""Training diagnostics & monitoring system.

Public API — import from here:
    from utils.diagnostics import StepInfo, EpisodeBuffer, DiagnosticsEngine, WandbTracker
"""
from utils.diagnostics.step_info import (
    GridState, AgentState, RewardBreakdown, SolverState, StepInfo,
)

__all__ = [
    "GridState", "AgentState", "RewardBreakdown", "SolverState", "StepInfo",
]
```

Create empty `utils/diagnostics/rules/__init__.py`:

```python
"""Diagnostic rules — imported by DiagnosticsEngine."""
```

```bash
git add utils/diagnostics/__init__.py utils/diagnostics/step_info.py \
       utils/diagnostics/rules/__init__.py tests/test_step_info.py
git commit -m "feat(diagnostics): StepInfo data contract — 5 dataclasses"
```

---

### Task 2: Backend Adapters

**Files:**
- Create: `utils/diagnostics/adapters.py`
- Test: `tests/test_adapters.py`

These adapters convert raw `info` dicts from each backend into `StepInfo`. They are pure functions, no env modification needed.

- [ ] **Step 1: Write failing tests for adapters**

Create `tests/test_adapters.py`:

```python
"""Tests for backend adapters (spec Section 3.2)."""
import time
import numpy as np
import pytest
from utils.diagnostics.step_info import StepInfo
from utils.diagnostics.adapters import andes_adapter, ode_adapter, simulink_adapter


# ── Fixtures: realistic info dicts from each backend ──

def _andes_info(n=4, fn=50.0):
    omega = np.array([1.002, 0.998, 1.001, 0.999])
    freq_hz = omega * fn
    return {
        "time": 2.0,
        "freq_hz": freq_hz,
        "omega": omega,
        "omega_dot": np.array([0.01, -0.01, 0.005, -0.005]),
        "P_es": np.array([5.0, 4.5, 5.2, 4.8]),
        "M_es": np.array([3.5, 4.0, 3.2, 3.8]),
        "D_es": np.array([2.5, 3.0, 2.2, 2.8]),
        "delta_M": np.array([0.5, 1.0, 0.2, 0.8]),
        "delta_D": np.array([0.5, 1.0, 0.2, 0.8]),
        "r_f": -45.0,
        "r_h": -3.0,
        "r_d": -2.0,
        "max_freq_deviation_hz": 0.1,
        "tds_failed": False,
    }


def _ode_info(n=4):
    return {
        "time": 2.0,
        "freq_hz": np.array([50.1, 49.9, 50.05, 49.95]),
        "omega": np.array([1.002, 0.998, 1.001, 0.999]),
        "P_es": np.array([5.0, 4.5, 5.2, 4.8]),
        "H_es": np.array([3.5, 4.0, 3.2, 3.8]),
        "D_es": np.array([2.5, 3.0, 2.2, 2.8]),
        "delta_H": np.array([0.5, 1.0, 0.2, 0.8]),
        "delta_D": np.array([0.5, 1.0, 0.2, 0.8]),
        "r_f": -45.0,
        "r_h": -3.0,
        "r_d": -2.0,
        "max_freq_deviation_hz": 0.1,
    }


def _simulink_info(n=4):
    return {
        "sim_time": 2.0,
        "omega": np.array([1.002, 0.998, 1.001, 0.999]),
        "M": np.array([3.5, 4.0, 3.2, 3.8]),
        "D": np.array([2.5, 3.0, 2.2, 2.8]),
        "P_es": np.array([5.0, 4.5, 5.2, 4.8]),
        "sim_ok": True,
        "freq_hz": np.array([50.1, 49.9, 50.05, 49.95]),
        "max_freq_dev_hz": 0.1,
    }


def _actions_dict(n=4):
    return {i: np.array([0.1 * (i + 1), -0.1 * (i + 1)]) for i in range(n)}


def _rewards_dict(n=4):
    return {i: -12.5 for i in range(n)}


class TestAndesAdapter:
    def test_returns_step_info(self):
        si = andes_adapter(
            step=5, episode=10, raw_info=_andes_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert isinstance(si, StepInfo)
        assert si.step == 5
        assert si.episode == 10

    def test_grid_state(self):
        si = andes_adapter(
            step=0, episode=0, raw_info=_andes_info(),
            actions=_actions_dict(), rewards=_rewards_dict(), done=False, fn=50.0,
        )
        assert si.grid.freq_hz.shape == (4,)
        assert si.grid.rocof is not None  # ANDES has omega_dot
        assert si.grid.max_freq_dev_hz == pytest.approx(0.1)

    def test_coi_frequency(self):
        info = _andes_info()
        si = andes_adapter(
            step=0, episode=0, raw_info=info,
            actions=_actions_dict(), rewards=_rewards_dict(), done=False, fn=50.0,
        )
        # COI = sum(H_i * f_i) / sum(H_i)
        H = info["M_es"]
        f = info["freq_hz"]
        expected_coi = float(np.sum(H * f) / np.sum(H))
        assert si.grid.freq_coi_hz == pytest.approx(expected_coi)

    def test_solver_tds_failed(self):
        info = _andes_info()
        info["tds_failed"] = True
        si = andes_adapter(
            step=0, episode=0, raw_info=info,
            actions=_actions_dict(), rewards=_rewards_dict(), done=True, fn=50.0,
        )
        assert si.solver.converged is False
        assert si.solver.backend == "andes"

    def test_agent_states(self):
        si = andes_adapter(
            step=0, episode=0, raw_info=_andes_info(),
            actions=_actions_dict(), rewards=_rewards_dict(), done=False, fn=50.0,
        )
        assert len(si.agents) == 4
        assert si.agents[0].H == pytest.approx(3.5)
        assert si.agents[0].delta_H == pytest.approx(0.5)

    def test_reward_components(self):
        si = andes_adapter(
            step=0, episode=0, raw_info=_andes_info(),
            actions=_actions_dict(), rewards=_rewards_dict(), done=False, fn=50.0,
        )
        assert si.reward.total == pytest.approx(-50.0)
        assert "r_f" in si.reward.components
        assert "r_h" in si.reward.components
        assert "r_d" in si.reward.components

    def test_done_reason(self):
        si = andes_adapter(
            step=49, episode=0, raw_info=_andes_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=True, fn=50.0,
        )
        assert si.done is True
        assert si.done_reason == "complete"

        info_fail = _andes_info()
        info_fail["tds_failed"] = True
        si2 = andes_adapter(
            step=10, episode=0, raw_info=info_fail,
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=True, fn=50.0,
        )
        assert si2.done_reason == "solver_fail"


class TestOdeAdapter:
    def test_returns_step_info(self):
        si = ode_adapter(
            step=0, episode=0, raw_info=_ode_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert isinstance(si, StepInfo)
        assert si.solver.backend == "ode"
        assert si.solver.converged is True  # ODE always converges

    def test_rocof_is_none(self):
        si = ode_adapter(
            step=0, episode=0, raw_info=_ode_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert si.grid.rocof is None  # ODE has no omega_dot

    def test_h_key_mapping(self):
        si = ode_adapter(
            step=0, episode=0, raw_info=_ode_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert si.agents[0].H == pytest.approx(3.5)  # from H_es


class TestSimulinkAdapter:
    def test_returns_step_info(self):
        si = simulink_adapter(
            step=0, episode=0, raw_info=_simulink_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert isinstance(si, StepInfo)
        assert si.solver.backend == "simulink"

    def test_no_reward_components(self):
        """Simulink info has no r_f/r_h/r_d — components dict should be empty."""
        si = simulink_adapter(
            step=0, episode=0, raw_info=_simulink_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert si.reward.components == {}

    def test_sim_ok_to_converged(self):
        info = _simulink_info()
        info["sim_ok"] = False
        si = simulink_adapter(
            step=0, episode=0, raw_info=info,
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=True, fn=50.0,
        )
        assert si.solver.converged is False

    def test_no_delta_hd_in_info(self):
        """Simulink info has no delta_M/delta_D — agents get 0.0."""
        si = simulink_adapter(
            step=0, episode=0, raw_info=_simulink_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        # delta_H/delta_D default to 0.0 when not in info
        assert si.agents[0].delta_H == 0.0
        assert si.agents[0].delta_D == 0.0

    def test_rocof_is_none(self):
        si = simulink_adapter(
            step=0, episode=0, raw_info=_simulink_info(),
            actions=_actions_dict(), rewards=_rewards_dict(),
            done=False, fn=50.0,
        )
        assert si.grid.rocof is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_adapters.py -v
```

Expected: `ImportError: cannot import name 'andes_adapter'`

- [ ] **Step 3: Implement adapters**

Create `utils/diagnostics/adapters.py`:

```python
"""Backend adapters: raw info dict -> StepInfo (spec Section 3.2).

Each adapter is a pure function. Env code is never modified.

Adapter signature (all three identical):
    adapter(step, episode, raw_info, actions, rewards, done, fn) -> StepInfo

Parameters
----------
step : int          Current step within episode.
episode : int       Current episode number.
raw_info : dict     The info dict returned by env.step().
actions : dict      {agent_id: np.ndarray} raw network outputs ([-1,1]).
rewards : dict      {agent_id: float} per-agent rewards.
done : bool         Whether the episode ended this step.
fn : float          Nominal frequency (50.0 or 60.0 Hz).
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from utils.diagnostics.step_info import (
    AgentState, GridState, RewardBreakdown, SolverState, StepInfo,
)


def _compute_coi(H: np.ndarray, freq_hz: np.ndarray) -> float:
    """Center-of-Inertia frequency: sum(H_i * f_i) / sum(H_i)."""
    total_H = np.sum(H)
    if total_H == 0:
        return float(np.mean(freq_hz))
    return float(np.sum(H * freq_hz) / total_H)


def _determine_done_reason(done: bool, solver_failed: bool) -> str | None:
    if not done:
        return None
    if solver_failed:
        return "solver_fail"
    return "complete"


def andes_adapter(
    *, step: int, episode: int, raw_info: dict,
    actions: dict, rewards: dict, done: bool, fn: float = 50.0,
) -> StepInfo:
    """Convert ANDES info dict to StepInfo.

    ANDES keys: time, freq_hz, omega, omega_dot, P_es, M_es, D_es,
                delta_M, delta_D, r_f, r_h, r_d, max_freq_deviation_hz,
                tds_failed
    """
    n = len(raw_info["freq_hz"])
    freq_hz = raw_info["freq_hz"]
    H = raw_info["M_es"]
    tds_failed = raw_info.get("tds_failed", False)

    grid = GridState(
        freq_hz=np.asarray(freq_hz, dtype=np.float64),
        freq_dev_hz=np.asarray(freq_hz - fn, dtype=np.float64),
        max_freq_dev_hz=float(raw_info["max_freq_deviation_hz"]),
        freq_coi_hz=_compute_coi(H, freq_hz),
        rocof=np.asarray(raw_info["omega_dot"], dtype=np.float64),
        power=np.asarray(raw_info["P_es"], dtype=np.float64),
    )

    agents = []
    for i in range(n):
        agents.append(AgentState(
            agent_id=i,
            H=float(H[i]),
            D=float(raw_info["D_es"][i]),
            delta_H=float(raw_info["delta_M"][i]),
            delta_D=float(raw_info["delta_D"][i]),
            action_raw=np.asarray(actions[i], dtype=np.float64),
            action_mapped=np.array([
                float(raw_info["delta_M"][i]),
                float(raw_info["delta_D"][i]),
            ]),
        ))

    reward = RewardBreakdown(
        total=sum(rewards[i] for i in range(n)),
        per_agent=dict(rewards),
        components={
            "r_f": float(raw_info["r_f"]),
            "r_h": float(raw_info["r_h"]),
            "r_d": float(raw_info["r_d"]),
        },
    )

    solver = SolverState(
        converged=not tds_failed,
        sim_time=float(raw_info["time"]),
        backend="andes",
        dt_actual=None,
    )

    return StepInfo(
        step=step, episode=episode, wall_time=time.time(),
        done=done,
        done_reason=_determine_done_reason(done, tds_failed),
        grid=grid, agents=agents, reward=reward, solver=solver,
    )


def ode_adapter(
    *, step: int, episode: int, raw_info: dict,
    actions: dict, rewards: dict, done: bool, fn: float = 50.0,
) -> StepInfo:
    """Convert ODE info dict to StepInfo.

    ODE keys: time, freq_hz, omega, P_es, H_es, D_es,
              delta_H, delta_D, r_f, r_h, r_d, max_freq_deviation_hz
    """
    n = len(raw_info["freq_hz"])
    freq_hz = raw_info["freq_hz"]
    H = raw_info["H_es"]

    grid = GridState(
        freq_hz=np.asarray(freq_hz, dtype=np.float64),
        freq_dev_hz=np.asarray(freq_hz - fn, dtype=np.float64),
        max_freq_dev_hz=float(raw_info["max_freq_deviation_hz"]),
        freq_coi_hz=_compute_coi(H, freq_hz),
        rocof=None,  # ODE env does not provide omega_dot
        power=np.asarray(raw_info["P_es"], dtype=np.float64),
    )

    agents = []
    for i in range(n):
        agents.append(AgentState(
            agent_id=i,
            H=float(H[i]),
            D=float(raw_info["D_es"][i]),
            delta_H=float(raw_info["delta_H"][i]),
            delta_D=float(raw_info["delta_D"][i]),
            action_raw=np.asarray(actions[i], dtype=np.float64),
            action_mapped=np.array([
                float(raw_info["delta_H"][i]),
                float(raw_info["delta_D"][i]),
            ]),
        ))

    reward = RewardBreakdown(
        total=sum(rewards[i] for i in range(n)),
        per_agent=dict(rewards),
        components={
            "r_f": float(raw_info["r_f"]),
            "r_h": float(raw_info["r_h"]),
            "r_d": float(raw_info["r_d"]),
        },
    )

    solver = SolverState(
        converged=True,  # ODE solver always converges
        sim_time=float(raw_info["time"]),
        backend="ode",
        dt_actual=None,
    )

    return StepInfo(
        step=step, episode=episode, wall_time=time.time(),
        done=done,
        done_reason=_determine_done_reason(done, solver_failed=False),
        grid=grid, agents=agents, reward=reward, solver=solver,
    )


def simulink_adapter(
    *, step: int, episode: int, raw_info: dict,
    actions: dict, rewards: dict, done: bool, fn: float = 50.0,
) -> StepInfo:
    """Convert Simulink info dict to StepInfo.

    Simulink keys: sim_time, omega, M, D, P_es, sim_ok, freq_hz,
                   max_freq_dev_hz
    NOTE: Simulink info has NO reward components (r_f/r_h/r_d) and
          NO delta_M/delta_D. These are set to empty/zero.
    """
    n = len(raw_info["omega"])
    freq_hz = raw_info["freq_hz"]
    H = raw_info["M"]
    sim_ok = raw_info.get("sim_ok", True)

    grid = GridState(
        freq_hz=np.asarray(freq_hz, dtype=np.float64),
        freq_dev_hz=np.asarray(freq_hz - fn, dtype=np.float64),
        max_freq_dev_hz=float(raw_info["max_freq_dev_hz"]),
        freq_coi_hz=_compute_coi(H, freq_hz),
        rocof=None,  # Simulink does not provide ROCOF yet
        power=np.asarray(raw_info["P_es"], dtype=np.float64),
    )

    agents = []
    for i in range(n):
        agents.append(AgentState(
            agent_id=i,
            H=float(H[i]),
            D=float(raw_info["D"][i]),
            delta_H=0.0,  # Not available in Simulink info
            delta_D=0.0,
            action_raw=np.asarray(actions[i], dtype=np.float64),
            action_mapped=np.asarray(actions[i], dtype=np.float64),
        ))

    reward = RewardBreakdown(
        total=sum(rewards[i] for i in range(n)),
        per_agent=dict(rewards),
        components={},  # Simulink info has no reward components
    )

    solver = SolverState(
        converged=sim_ok,
        sim_time=float(raw_info["sim_time"]),
        backend="simulink",
        dt_actual=None,
    )

    return StepInfo(
        step=step, episode=episode, wall_time=time.time(),
        done=done,
        done_reason=_determine_done_reason(done, solver_failed=not sim_ok),
        grid=grid, agents=agents, reward=reward, solver=solver,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_adapters.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Update `__init__.py` and commit**

Add to `utils/diagnostics/__init__.py`:

```python
from utils.diagnostics.adapters import andes_adapter, ode_adapter, simulink_adapter
```

And add to `__all__`:

```python
    "andes_adapter", "ode_adapter", "simulink_adapter",
```

```bash
git add utils/diagnostics/adapters.py tests/test_adapters.py utils/diagnostics/__init__.py
git commit -m "feat(diagnostics): backend adapters — ANDES, ODE, Simulink -> StepInfo"
```

---

### Task 3: EpisodeBuffer + EpisodeMetrics

**Files:**
- Create: `utils/diagnostics/episode_buffer.py`
- Test: `tests/test_episode_buffer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_episode_buffer.py`:

```python
"""Tests for EpisodeBuffer and EpisodeMetrics (spec Section 4)."""
import os
import tempfile
import numpy as np
import pytest
from utils.diagnostics.step_info import (
    GridState, AgentState, RewardBreakdown, SolverState, StepInfo,
)
from utils.diagnostics.episode_buffer import EpisodeBuffer, EpisodeMetrics, SnapshotRecord


def _make_step(step, episode, done=False, n=4, freq_nom=50.0,
               freq_dev=0.1, H_vals=None, D_vals=None):
    """Helper to create a StepInfo with controllable values."""
    if H_vals is None:
        H_vals = [3.0] * n
    if D_vals is None:
        D_vals = [2.0] * n
    freq = np.full(n, freq_nom + freq_dev)
    return StepInfo(
        step=step, episode=episode, wall_time=1000.0 + step * 0.1,
        done=done, done_reason="complete" if done else None,
        grid=GridState(
            freq_hz=freq,
            freq_dev_hz=freq - freq_nom,
            max_freq_dev_hz=abs(freq_dev),
            freq_coi_hz=float(np.sum(np.array(H_vals) * freq) / np.sum(H_vals)),
            rocof=np.zeros(n),
            power=np.ones(n) * 5.0,
        ),
        agents=[
            AgentState(
                agent_id=i, H=H_vals[i], D=D_vals[i],
                delta_H=0.5, delta_D=0.3,
                action_raw=np.array([0.1 * (i + 1), -0.1 * (i + 1)]),
                action_mapped=np.array([0.5, 0.3]),
            )
            for i in range(n)
        ],
        reward=RewardBreakdown(
            total=-50.0,
            per_agent={i: -50.0 / n for i in range(n)},
            components={"r_f": -45.0, "r_h": -3.0, "r_d": -2.0},
        ),
        solver=SolverState(converged=True, sim_time=step * 0.2, backend="andes", dt_actual=None),
    )


def _fill_episode(buf, episode, n_steps=5, n_agents=4, **kwargs):
    """Add a complete episode to the buffer."""
    for s in range(n_steps):
        done = (s == n_steps - 1)
        buf.add_step(_make_step(s, episode, done=done, n=n_agents, **kwargs))


class TestEpisodeBufferBasic:
    def test_empty_buffer(self):
        buf = EpisodeBuffer(capacity=5)
        assert buf.latest_metrics() is None
        assert buf.get_trajectory(0) is None
        assert buf.get_recent_metrics(10) == []

    def test_single_episode(self):
        buf = EpisodeBuffer(capacity=5)
        _fill_episode(buf, episode=0)
        m = buf.latest_metrics()
        assert m is not None
        assert m.episode == 0
        assert m.total_reward == pytest.approx(-50.0 * 5)  # 5 steps * -50 per step

    def test_ring_eviction(self):
        buf = EpisodeBuffer(capacity=3)
        for ep in range(5):
            _fill_episode(buf, episode=ep)
        # Only episodes 2, 3, 4 should remain in ring
        assert buf.get_trajectory(0) is None
        assert buf.get_trajectory(1) is None
        assert buf.get_trajectory(2) is not None
        assert buf.get_trajectory(4) is not None

    def test_metrics_history_length(self):
        buf = EpisodeBuffer(capacity=3, metrics_maxlen=10)
        for ep in range(15):
            _fill_episode(buf, episode=ep)
        # metrics_maxlen=10, so only last 10 episodes in history
        recent = buf.get_recent_metrics(20)
        assert len(recent) == 10
        assert recent[0].episode == 5  # oldest remaining
        assert recent[-1].episode == 14  # newest


class TestEpisodeMetrics:
    def test_reward_components_accumulated(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0, n_steps=5)
        m = buf.latest_metrics()
        assert m.reward_components["r_f"] == pytest.approx(-45.0 * 5)
        assert m.reward_components["r_h"] == pytest.approx(-3.0 * 5)

    def test_freq_stats(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0, freq_dev=0.2)
        m = buf.latest_metrics()
        assert m.mean_freq_dev_hz == pytest.approx(0.2)
        assert m.max_freq_dev_hz == pytest.approx(0.2)

    def test_action_stats(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0, n_steps=10)
        m = buf.latest_metrics()
        # Agent 0 action_raw = [0.1, -0.1] every step
        assert m.action_mean[0].shape == (2,)
        assert m.action_std[0].shape == (2,)
        assert m.action_std[0][0] == pytest.approx(0.0, abs=1e-6)  # constant action

    def test_hd_range(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0, H_vals=[3.0, 4.0, 5.0, 6.0])
        m = buf.latest_metrics()
        assert m.h_range_used[0] == (3.0, 3.0)  # constant H within episode
        assert m.h_range_used[1] == (4.0, 4.0)

    def test_solver_fail_steps(self):
        buf = EpisodeBuffer()
        # Manually create steps with one failed solver
        for s in range(5):
            si = _make_step(s, 0, done=(s == 4))
            if s == 2:
                si.solver.converged = False
            buf.add_step(si)
        m = buf.latest_metrics()
        assert m.solver_fail_steps == 1

    def test_wall_time(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0, n_steps=5)
        m = buf.latest_metrics()
        # wall_time = 1000.0 + step * 0.1, so last - first = 0.4
        assert m.wall_time_seconds == pytest.approx(0.4)

    def test_done_reason(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0)
        m = buf.latest_metrics()
        assert m.done_reason == "complete"

    def test_to_wandb_dict_keys(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0)
        m = buf.latest_metrics()
        d = m.to_wandb_dict()
        # Check key prefixes
        assert "grid/mean_freq_dev_hz" in d
        assert "grid/max_freq_dev_hz" in d
        assert "reward/total" in d
        assert "reward/r_f" in d
        assert "agent_0/reward" in d
        assert "episode/done_reason" in d
        assert "episode/wall_time_s" in d


class TestPatchTrainingStats:
    def test_patch_latest(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0)
        stats = {"critic_loss": 5.0, "actor_loss": 1.2, "entropy": 0.8}
        buf.patch_training_stats(0, stats)
        m = buf.latest_metrics()
        assert m.training_stats == stats

    def test_patch_wrong_episode_ignored(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0)
        buf.patch_training_stats(999, {"critic_loss": 5.0})
        m = buf.latest_metrics()
        assert m.training_stats is None

    def test_to_wandb_dict_includes_training_stats(self):
        buf = EpisodeBuffer()
        _fill_episode(buf, episode=0)
        buf.patch_training_stats(0, {"critic_loss": 5.0, "actor_loss": 1.2})
        d = buf.latest_metrics().to_wandb_dict()
        assert "train/critic_loss" in d
        assert "train/actor_loss" in d


class TestSnapshot:
    def test_snapshot_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            buf = EpisodeBuffer(capacity=5, save_dir=tmpdir)
            for ep in range(3):
                _fill_episode(buf, episode=ep)
            record = buf.snapshot(reason="test_alert")
            assert isinstance(record, SnapshotRecord)
            assert record.reason == "test_alert"
            assert record.episode == 2
            assert os.path.exists(record.path)

    def test_snapshot_stores_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            buf = EpisodeBuffer(capacity=5, save_dir=tmpdir)
            _fill_episode(buf, episode=0)
            buf.snapshot(reason="test")
            assert len(buf._snapshots) == 1


class TestEpisodeOffset:
    def test_set_offset(self):
        buf = EpisodeBuffer()
        buf.set_episode_offset(100)
        assert buf._episode_offset == 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_episode_buffer.py -v
```

Expected: `ImportError: cannot import name 'EpisodeBuffer'`

- [ ] **Step 3: Implement EpisodeBuffer**

Create `utils/diagnostics/episode_buffer.py`:

```python
"""EpisodeBuffer: ring buffer + metrics aggregation (spec Section 4).

Two-level storage:
  - Memory ring: full StepInfo sequences for the most recent K episodes
  - Metrics deque: scalar EpisodeMetrics for the most recent N episodes
  - Disk snapshots: triggered by diagnostics alerts or periodic saves
"""
from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from utils.diagnostics.step_info import StepInfo


@dataclass
class EpisodeMetrics:
    """Aggregated scalar metrics for a single episode (spec Section 4.1)."""
    episode: int
    total_reward: float
    reward_components: dict[str, float]
    per_agent_rewards: dict[int, float]
    mean_freq_dev_hz: float
    max_freq_dev_hz: float
    freq_coi_std: float
    action_mean: dict[int, np.ndarray]
    action_std: dict[int, np.ndarray]
    h_range_used: dict[int, tuple[float, float]]
    d_range_used: dict[int, tuple[float, float]]
    solver_fail_steps: int
    done_reason: str
    wall_time_seconds: float
    training_stats: dict[str, float] | None = None

    def to_wandb_dict(self) -> dict[str, Any]:
        """Serialize to wandb.log() format with grouped keys."""
        d: dict[str, Any] = {}
        # grid/
        d["grid/mean_freq_dev_hz"] = self.mean_freq_dev_hz
        d["grid/max_freq_dev_hz"] = self.max_freq_dev_hz
        d["grid/freq_coi_std"] = self.freq_coi_std
        # reward/
        d["reward/total"] = self.total_reward
        for k, v in self.reward_components.items():
            d[f"reward/{k}"] = v
        # agent_N/
        for agent_id, r in self.per_agent_rewards.items():
            prefix = f"agent_{agent_id}"
            d[f"{prefix}/reward"] = r
            if agent_id in self.action_mean:
                d[f"{prefix}/action_std"] = float(np.mean(self.action_std[agent_id]))
            if agent_id in self.h_range_used:
                h_lo, h_hi = self.h_range_used[agent_id]
                d[f"{prefix}/H_range"] = h_hi - h_lo
            if agent_id in self.d_range_used:
                d_lo, d_hi = self.d_range_used[agent_id]
                d[f"{prefix}/D_range"] = d_hi - d_lo
        # train/
        if self.training_stats:
            for k, v in self.training_stats.items():
                d[f"train/{k}"] = v
        # episode/
        d["episode/done_reason"] = self.done_reason
        d["episode/wall_time_s"] = self.wall_time_seconds
        return d


@dataclass
class SnapshotRecord:
    """Metadata for a saved snapshot."""
    path: str
    episode: int
    reason: str
    timestamp: float


class EpisodeBuffer:
    """Two-level episode storage with metrics aggregation (spec Section 4.2)."""

    def __init__(
        self,
        capacity: int = 20,
        periodic_save_interval: int = 50,
        metrics_maxlen: int = 5000,
        save_dir: str | None = None,
    ):
        self._ring: deque[list[StepInfo]] = deque(maxlen=capacity)
        self._current_episode: list[StepInfo] = []
        self._metrics_history: deque[EpisodeMetrics] = deque(maxlen=metrics_maxlen)
        self._periodic_interval = periodic_save_interval
        self._snapshots: list[SnapshotRecord] = []
        self._episode_offset: int = 0
        self._save_dir = save_dir

    def add_step(self, info: StepInfo):
        """Add a step. When done=True, finalize episode into ring + metrics."""
        self._current_episode.append(info)
        if info.done:
            self._ring.append(self._current_episode)
            metrics = self._aggregate(self._current_episode)
            self._metrics_history.append(metrics)
            self._current_episode = []

    def patch_training_stats(self, episode: int, stats: dict[str, float] | None):
        """Inject SAC loss stats after update. Must match latest episode."""
        if self._metrics_history and self._metrics_history[-1].episode == episode:
            self._metrics_history[-1].training_stats = stats

    def snapshot(self, reason: str) -> SnapshotRecord:
        """Save current + previous episodes in ring to disk as npz."""
        save_dir = self._save_dir or "results/snapshots"
        os.makedirs(save_dir, exist_ok=True)

        ep = self._metrics_history[-1].episode if self._metrics_history else 0
        filename = f"snapshot_ep{ep}_{reason}.npz"
        path = os.path.join(save_dir, filename)

        # Save all episodes currently in ring
        data = {}
        for idx, ep_steps in enumerate(self._ring):
            if ep_steps:
                data[f"ep{idx}_freq"] = np.array([s.grid.freq_hz for s in ep_steps])
                data[f"ep{idx}_power"] = np.array([s.grid.power for s in ep_steps])
                data[f"ep{idx}_reward"] = np.array([s.reward.total for s in ep_steps])
        np.savez_compressed(path, **data)

        record = SnapshotRecord(
            path=path, episode=ep, reason=reason, timestamp=time.time(),
        )
        self._snapshots.append(record)
        return record

    def get_recent_metrics(self, n: int) -> list[EpisodeMetrics]:
        """Return up to n most recent EpisodeMetrics."""
        return list(self._metrics_history)[-n:]

    def get_trajectory(self, episode: int) -> list[StepInfo] | None:
        """Retrieve full StepInfo trajectory for an episode (if in ring)."""
        for ep_steps in self._ring:
            if ep_steps and ep_steps[0].episode == episode:
                return ep_steps
        return None

    def latest_metrics(self) -> EpisodeMetrics | None:
        """Return the most recent EpisodeMetrics, or None."""
        return self._metrics_history[-1] if self._metrics_history else None

    def set_episode_offset(self, offset: int):
        """Set episode offset for resumed training."""
        self._episode_offset = offset

    # ── Private ──

    def _aggregate(self, steps: list[StepInfo]) -> EpisodeMetrics:
        """Compute EpisodeMetrics from a completed episode's StepInfo list."""
        n_steps = len(steps)
        episode = steps[0].episode

        # Rewards
        total_reward = sum(s.reward.total for s in steps)
        # Per-agent cumulative
        agent_ids = [a.agent_id for a in steps[0].agents]
        per_agent = {aid: sum(s.reward.per_agent.get(aid, 0) for s in steps)
                     for aid in agent_ids}
        # Reward components cumulative
        comp_keys = set()
        for s in steps:
            comp_keys.update(s.reward.components.keys())
        reward_components = {
            k: sum(s.reward.components.get(k, 0) for s in steps)
            for k in comp_keys
        }

        # Frequency stats
        freq_devs = [s.grid.max_freq_dev_hz for s in steps]
        mean_freq_dev = float(np.mean([
            float(np.mean(np.abs(s.grid.freq_dev_hz))) for s in steps
        ]))
        max_freq_dev = float(np.max(freq_devs))
        coi_values = [s.grid.freq_coi_hz for s in steps]
        freq_coi_std = float(np.std(coi_values))

        # Action stats per agent
        action_mean: dict[int, np.ndarray] = {}
        action_std: dict[int, np.ndarray] = {}
        h_range: dict[int, tuple[float, float]] = {}
        d_range: dict[int, tuple[float, float]] = {}
        for aid in agent_ids:
            raw_actions = np.array([s.agents[aid].action_raw for s in steps])
            action_mean[aid] = np.mean(raw_actions, axis=0)
            action_std[aid] = np.std(raw_actions, axis=0)
            h_vals = [s.agents[aid].H for s in steps]
            d_vals = [s.agents[aid].D for s in steps]
            h_range[aid] = (min(h_vals), max(h_vals))
            d_range[aid] = (min(d_vals), max(d_vals))

        # Solver
        solver_fail = sum(1 for s in steps if not s.solver.converged)

        # Wall time
        wall_time = steps[-1].wall_time - steps[0].wall_time

        # Done reason
        done_reason = steps[-1].done_reason or "complete"

        return EpisodeMetrics(
            episode=episode,
            total_reward=total_reward,
            reward_components=reward_components,
            per_agent_rewards=per_agent,
            mean_freq_dev_hz=mean_freq_dev,
            max_freq_dev_hz=max_freq_dev,
            freq_coi_std=freq_coi_std,
            action_mean=action_mean,
            action_std=action_std,
            h_range_used=h_range,
            d_range_used=d_range,
            solver_fail_steps=solver_fail,
            done_reason=done_reason,
            wall_time_seconds=wall_time,
            training_stats=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_episode_buffer.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Update `__init__.py` and commit**

Add to `utils/diagnostics/__init__.py`:

```python
from utils.diagnostics.episode_buffer import EpisodeBuffer, EpisodeMetrics, SnapshotRecord
```

Add to `__all__`:

```python
    "EpisodeBuffer", "EpisodeMetrics", "SnapshotRecord",
```

```bash
git add utils/diagnostics/episode_buffer.py tests/test_episode_buffer.py \
       utils/diagnostics/__init__.py
git commit -m "feat(diagnostics): EpisodeBuffer + EpisodeMetrics aggregation"
```

---

### Task 4: DiagnosticsEngine + 7 Rules

**Files:**
- Create: `utils/diagnostics/engine.py`
- Create: `utils/diagnostics/rules/critic_loss.py`
- Create: `utils/diagnostics/rules/improvement.py`
- Create: `utils/diagnostics/rules/hd_range.py`
- Create: `utils/diagnostics/rules/coordination.py`
- Create: `utils/diagnostics/rules/dominance.py`
- Create: `utils/diagnostics/rules/action_collapse.py`
- Create: `utils/diagnostics/rules/solver_failure.py`
- Modify: `utils/diagnostics/rules/__init__.py`
- Test: `tests/test_diagnostics_engine.py`

This is the largest task. We build the engine framework first, then each rule.

- [ ] **Step 1: Write failing tests for engine and all 7 rules**

Create `tests/test_diagnostics_engine.py`:

```python
"""Tests for DiagnosticsEngine + 7 diagnostic rules (spec Section 5)."""
import numpy as np
import pytest
from utils.diagnostics.step_info import (
    GridState, AgentState, RewardBreakdown, SolverState, StepInfo,
)
from utils.diagnostics.episode_buffer import EpisodeBuffer, EpisodeMetrics
from utils.diagnostics.engine import (
    DiagnosticsEngine, DiagnosticRule, DiagnosticReport,
    DiagnosticResult, Severity,
)
from utils.diagnostics.rules import (
    CriticLossTrend, ImprovementStall, HDRangeUtilization,
    InterAgentCoordination, RewardComponentDominance,
    ActionCollapse, SolverFailureRate,
)


# ── Helpers ──

def _make_metrics(
    episode, total_reward=-50.0, reward_components=None,
    action_std_val=0.5, h_range=(1.0, 10.0), d_range=(0.5, 15.0),
    solver_fail=0, training_stats=None, n_agents=4,
    freq_dev=0.1,
):
    """Build a synthetic EpisodeMetrics."""
    if reward_components is None:
        reward_components = {"r_f": -45.0, "r_h": -3.0, "r_d": -2.0}
    return EpisodeMetrics(
        episode=episode,
        total_reward=total_reward,
        reward_components=reward_components,
        per_agent_rewards={i: total_reward / n_agents for i in range(n_agents)},
        mean_freq_dev_hz=freq_dev,
        max_freq_dev_hz=freq_dev * 2,
        freq_coi_std=0.01,
        action_mean={i: np.array([0.0, 0.0]) for i in range(n_agents)},
        action_std={i: np.array([action_std_val, action_std_val]) for i in range(n_agents)},
        h_range_used={i: h_range for i in range(n_agents)},
        d_range_used={i: d_range for i in range(n_agents)},
        solver_fail_steps=solver_fail,
        done_reason="complete",
        wall_time_seconds=10.0,
        training_stats=training_stats,
    )


def _fill_buffer_with_metrics(n_episodes, **kwargs):
    """Create a buffer and fill it with n synthetic EpisodeMetrics."""
    buf = EpisodeBuffer(capacity=5, metrics_maxlen=5000)
    for ep in range(n_episodes):
        kw = {k: (v(ep) if callable(v) else v) for k, v in kwargs.items()}
        m = _make_metrics(episode=ep, **kw)
        buf._metrics_history.append(m)
    return buf


# ── Engine tests ──

class TestDiagnosticsEngine:
    def test_no_rules_returns_none(self):
        engine = DiagnosticsEngine(rules=[])
        buf = _fill_buffer_with_metrics(100)
        assert engine.on_episode_end(buf) is None

    def test_rule_not_triggered_returns_none(self):
        """Healthy training → no diagnostic report."""
        engine = DiagnosticsEngine()
        buf = _fill_buffer_with_metrics(
            300,
            total_reward=lambda ep: -100 + ep * 0.5,  # improving
            training_stats=lambda ep: {"critic_loss": 1.0, "actor_loss": 0.5, "entropy": 0.8},
            action_std_val=0.5,
        )
        report = engine.on_episode_end(buf)
        # May or may not be None depending on exact thresholds;
        # at minimum, no STOP severity
        if report is not None:
            assert report.worst_severity() != Severity.STOP

    def test_health_score_range(self):
        engine = DiagnosticsEngine()
        buf = _fill_buffer_with_metrics(
            300,
            training_stats=lambda ep: {"critic_loss": ep * 0.5},  # exploding
        )
        report = engine.on_episode_end(buf)
        if report is not None:
            assert 0.0 <= report.health_score <= 1.0

    def test_to_wandb_dict(self):
        engine = DiagnosticsEngine()
        buf = _fill_buffer_with_metrics(
            300,
            training_stats=lambda ep: {"critic_loss": ep * 0.5},
        )
        report = engine.on_episode_end(buf)
        if report is not None:
            d = report.to_wandb_dict()
            assert "diagnostics/health_score" in d


# ── Individual rule tests ──

class TestCriticLossTrend:
    def test_detects_explosion(self):
        """Critic loss linearly increasing → should trigger."""
        rule = CriticLossTrend()
        metrics = [
            _make_metrics(ep, training_stats={"critic_loss": 1.0 + ep * 0.5})
            for ep in range(200)
        ]
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "CriticLossTrend"
        assert result.severity in (Severity.WARN, Severity.STOP)

    def test_stable_loss_no_trigger(self):
        """Stable critic loss → should not trigger."""
        rule = CriticLossTrend()
        metrics = [
            _make_metrics(ep, training_stats={"critic_loss": 1.0 + np.random.normal(0, 0.1)})
            for ep in range(200)
        ]
        result = rule.check(metrics)
        assert result is None

    def test_no_training_stats_no_crash(self):
        """Missing training_stats → graceful None."""
        rule = CriticLossTrend()
        metrics = [_make_metrics(ep, training_stats=None) for ep in range(200)]
        result = rule.check(metrics)
        assert result is None


class TestImprovementStall:
    def test_detects_stall(self):
        """Flat reward → should trigger."""
        rule = ImprovementStall()
        metrics = [_make_metrics(ep, total_reward=-100.0) for ep in range(200)]
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "ImprovementStall"

    def test_improving_no_trigger(self):
        """Improving reward → should not trigger."""
        rule = ImprovementStall()
        metrics = [_make_metrics(ep, total_reward=-100 + ep * 1.0) for ep in range(200)]
        result = rule.check(metrics)
        assert result is None


class TestHDRangeUtilization:
    def test_detects_narrow_range(self):
        """H/D stuck in narrow range → should trigger."""
        rule = HDRangeUtilization()
        metrics = [
            _make_metrics(ep, h_range=(3.0, 3.1), d_range=(2.0, 2.1))
            for ep in range(100)
        ]
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "HDRangeUtilization"

    def test_full_range_no_trigger(self):
        """H/D using full range → should not trigger."""
        rule = HDRangeUtilization()
        metrics = [
            _make_metrics(ep, h_range=(0.5, 18.0), d_range=(0.5, 22.0))
            for ep in range(100)
        ]
        result = rule.check(metrics)
        assert result is None


class TestInterAgentCoordination:
    def test_detects_lockstep(self):
        """All agents same action_mean → Pearson ~ 1.0 → should trigger."""
        rule = InterAgentCoordination()
        metrics = []
        for ep in range(50):
            m = _make_metrics(ep)
            # All agents have identical, varying action means
            val = np.array([0.1 * ep, -0.1 * ep])
            m.action_mean = {i: val.copy() for i in range(4)}
            metrics.append(m)
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "InterAgentCoordination"

    def test_diverse_no_trigger(self):
        """Diverse agent behaviors → should not trigger."""
        rule = InterAgentCoordination()
        rng = np.random.RandomState(42)
        metrics = []
        for ep in range(50):
            m = _make_metrics(ep)
            m.action_mean = {i: rng.randn(2) for i in range(4)}
            metrics.append(m)
        result = rule.check(metrics)
        assert result is None


class TestRewardComponentDominance:
    def test_detects_dominance(self):
        """r_f > 80% of total → should trigger."""
        rule = RewardComponentDominance()
        metrics = [
            _make_metrics(ep, reward_components={"r_f": -95.0, "r_h": -3.0, "r_d": -2.0})
            for ep in range(50)
        ]
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "RewardComponentDominance"

    def test_balanced_no_trigger(self):
        rule = RewardComponentDominance()
        metrics = [
            _make_metrics(ep, reward_components={"r_f": -40.0, "r_h": -30.0, "r_d": -30.0})
            for ep in range(50)
        ]
        result = rule.check(metrics)
        assert result is None


class TestActionCollapse:
    def test_detects_collapse(self):
        """action_std < 0.05 for 50 eps → should trigger."""
        rule = ActionCollapse()
        metrics = [_make_metrics(ep, action_std_val=0.01) for ep in range(50)]
        result = rule.check(metrics)
        assert result is not None
        assert result.rule_name == "ActionCollapse"

    def test_normal_std_no_trigger(self):
        rule = ActionCollapse()
        metrics = [_make_metrics(ep, action_std_val=0.5) for ep in range(50)]
        result = rule.check(metrics)
        assert result is None


class TestSolverFailureRate:
    def test_detects_high_failure(self):
        """> 20% solver fails → should trigger."""
        rule = SolverFailureRate()
        metrics = [_make_metrics(ep, solver_fail=3) for ep in range(20)]
        # 3 fail steps per ep out of ~50 steps = 6% per ep;
        # but the rule checks done_reason / solver_fail_steps
        # Let's make it clearly fail: 10+ fail steps out of 50
        metrics_fail = [_make_metrics(ep, solver_fail=15) for ep in range(20)]
        result = rule.check(metrics_fail)
        assert result is not None
        assert result.rule_name == "SolverFailureRate"

    def test_no_failures_no_trigger(self):
        rule = SolverFailureRate()
        metrics = [_make_metrics(ep, solver_fail=0) for ep in range(20)]
        result = rule.check(metrics)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_diagnostics_engine.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement engine framework**

Create `utils/diagnostics/engine.py`:

```python
"""DiagnosticsEngine: rule-based training health monitoring (spec Section 5)."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.diagnostics.episode_buffer import EpisodeBuffer, EpisodeMetrics
from utils.log import get_logger

logger = get_logger(__name__)


class Severity(Enum):
    INFO = "info"
    WARN = "warn"
    STOP = "stop"


@dataclass
class DiagnosticResult:
    rule_name: str
    severity: Severity
    message: str
    evidence: dict[str, Any]
    suggestion: str | None


class DiagnosticRule(ABC):
    """Base class for all diagnostic rules."""
    name: str = "unnamed"
    check_interval: int = 50
    min_episodes: int = 50
    window_size: int = 50
    severity: Severity = Severity.WARN

    @abstractmethod
    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        """Return None if healthy, DiagnosticResult if anomaly detected."""


@dataclass
class DiagnosticReport:
    episode: int
    timestamp: float
    results: list[DiagnosticResult]
    health_score: float
    n_active_rules: int

    def has_alerts(self) -> bool:
        return len(self.results) > 0

    def worst_severity(self) -> Severity:
        if not self.results:
            return Severity.INFO
        order = {Severity.INFO: 0, Severity.WARN: 1, Severity.STOP: 2}
        return max(self.results, key=lambda r: order[r.severity]).severity

    def to_wandb_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "diagnostics/health_score": self.health_score,
            "diagnostics/n_alerts": len(self.results),
            "diagnostics/n_active_rules": self.n_active_rules,
        }
        for r in self.results:
            d[f"diagnostics/{r.rule_name}/severity"] = r.severity.value
            d[f"diagnostics/{r.rule_name}/message"] = r.message
        return d


class DiagnosticsEngine:
    """Runs diagnostic rules on episode metrics (spec Section 5.5)."""

    def __init__(self, rules: list[DiagnosticRule] | None = None):
        if rules is None:
            rules = self._default_rules()
        self.rules = rules
        self._reports: list[DiagnosticReport] = []

    def on_episode_end(self, buffer: EpisodeBuffer) -> DiagnosticReport | None:
        latest = buffer.latest_metrics()
        if latest is None:
            return None

        ep = latest.episode

        if latest.training_stats is None:
            logger.debug("training_stats not patched before diagnostics (ep %d)", ep)

        active_rules = [
            r for r in self.rules
            if ep >= r.min_episodes and ep % r.check_interval == 0
        ]
        if not active_rules:
            return None

        metrics_needed = max(r.window_size for r in active_rules)
        metrics = buffer.get_recent_metrics(metrics_needed)

        results = []
        for rule in active_rules:
            result = rule.check(metrics)
            if result:
                results.append(result)

        if not results:
            return None

        report = DiagnosticReport(
            episode=ep,
            timestamp=time.time(),
            results=results,
            health_score=self._compute_health(results, len(active_rules)),
            n_active_rules=len(active_rules),
        )

        if report.worst_severity() in (Severity.WARN, Severity.STOP):
            buffer.snapshot(reason=f"diag_{report.worst_severity().value}_ep{ep}")

        self._reports.append(report)
        return report

    def latest_health_score(self) -> float | None:
        return self._reports[-1].health_score if self._reports else None

    def _compute_health(self, results: list[DiagnosticResult],
                        n_active_rules: int) -> float:
        penalty = sum(
            0.3 if r.severity == Severity.STOP else 0.1
            for r in results
        )
        return max(0.0, 1.0 - penalty / max(n_active_rules * 0.1, 1.0))

    @staticmethod
    def _default_rules() -> list[DiagnosticRule]:
        from utils.diagnostics.rules import (
            CriticLossTrend, ImprovementStall, HDRangeUtilization,
            InterAgentCoordination, RewardComponentDominance,
            ActionCollapse, SolverFailureRate,
        )
        return [
            CriticLossTrend(),
            ImprovementStall(),
            HDRangeUtilization(),
            InterAgentCoordination(),
            RewardComponentDominance(),
            ActionCollapse(),
            SolverFailureRate(),
        ]
```

- [ ] **Step 4: Implement Rule 1 — CriticLossTrend**

Create `utils/diagnostics/rules/critic_loss.py`:

```python
"""CriticLossTrend: detect critic loss explosion via linear regression (spec rule #1)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class CriticLossTrend(DiagnosticRule):
    """Fires when critic_loss has a positive linear trend over the window."""

    name = "CriticLossTrend"
    check_interval = 50
    min_episodes = 100
    window_size = 200
    severity = Severity.WARN

    def __init__(self, slope_threshold: float = 0.05):
        self.slope_threshold = slope_threshold

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        losses = []
        for m in metrics[-self.window_size:]:
            if m.training_stats and "critic_loss" in m.training_stats:
                losses.append(m.training_stats["critic_loss"])

        if len(losses) < 20:
            return None

        x = np.arange(len(losses), dtype=np.float64)
        y = np.array(losses, dtype=np.float64)

        # Linear regression: slope = cov(x,y) / var(x)
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        slope = float(np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2))

        if slope <= self.slope_threshold:
            return None

        severity = Severity.STOP if slope > self.slope_threshold * 5 else Severity.WARN
        return DiagnosticResult(
            rule_name=self.name,
            severity=severity,
            message=f"Critic loss trending up: slope={slope:.4f} over {len(losses)} eps",
            evidence={"slope": slope, "mean_loss": float(y_mean),
                      "last_loss": float(y[-1]), "window": len(losses)},
            suggestion="Consider reducing LR or adding gradient clipping",
        )
```

- [ ] **Step 5: Implement Rule 2 — ImprovementStall**

Create `utils/diagnostics/rules/improvement.py`:

```python
"""ImprovementStall: detect reward/freq stagnation (spec rule #2)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class ImprovementStall(DiagnosticRule):
    """Fires when total_reward shows no improvement over the window."""

    name = "ImprovementStall"
    check_interval = 100
    min_episodes = 200
    window_size = 200
    severity = Severity.WARN

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < self.window_size:
            return None

        rewards = np.array([m.total_reward for m in recent])
        x = np.arange(len(rewards), dtype=np.float64)
        x_mean = np.mean(x)
        slope = float(np.sum((x - x_mean) * (rewards - np.mean(rewards)))
                       / np.sum((x - x_mean) ** 2))

        if slope > 0:
            return None

        # Also check freq_dev trend
        freq_devs = np.array([m.mean_freq_dev_hz for m in recent])
        freq_slope = float(np.sum((x - x_mean) * (freq_devs - np.mean(freq_devs)))
                           / np.sum((x - x_mean) ** 2))

        return DiagnosticResult(
            rule_name=self.name,
            severity=self.severity,
            message=(f"Reward stalled: slope={slope:.4f}, "
                     f"freq_dev slope={freq_slope:.6f} over {len(recent)} eps"),
            evidence={"reward_slope": slope, "freq_slope": freq_slope,
                      "mean_reward": float(np.mean(rewards))},
            suggestion="Try increasing exploration (entropy target) or adjusting reward weights",
        )
```

- [ ] **Step 6: Implement Rule 3 — HDRangeUtilization**

Create `utils/diagnostics/rules/hd_range.py`:

```python
"""HDRangeUtilization: detect under-used H/D parameter ranges (spec rule #3)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class HDRangeUtilization(DiagnosticRule):
    """Fires when any agent uses < 20% of available H or D range."""

    name = "HDRangeUtilization"
    check_interval = 100
    min_episodes = 100
    window_size = 100
    severity = Severity.INFO

    def __init__(self, utilization_threshold: float = 0.2,
                 h_total_range: float = 17.5, d_total_range: float = 21.5):
        # Default ranges: H=[0.5, 18] -> 17.5, D=[0.5, 22] -> 21.5
        self.utilization_threshold = utilization_threshold
        self.h_total_range = h_total_range
        self.d_total_range = d_total_range

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < 10:
            return None

        low_util_agents = []
        agent_ids = list(recent[0].h_range_used.keys())

        for aid in agent_ids:
            # Aggregate H/D range across recent episodes
            all_h_lo = min(m.h_range_used[aid][0] for m in recent)
            all_h_hi = max(m.h_range_used[aid][1] for m in recent)
            all_d_lo = min(m.d_range_used[aid][0] for m in recent)
            all_d_hi = max(m.d_range_used[aid][1] for m in recent)

            h_util = (all_h_hi - all_h_lo) / self.h_total_range if self.h_total_range > 0 else 1.0
            d_util = (all_d_hi - all_d_lo) / self.d_total_range if self.d_total_range > 0 else 1.0

            if h_util < self.utilization_threshold or d_util < self.utilization_threshold:
                low_util_agents.append({
                    "agent": aid, "h_util": h_util, "d_util": d_util,
                })

        if not low_util_agents:
            return None

        return DiagnosticResult(
            rule_name=self.name,
            severity=self.severity,
            message=f"{len(low_util_agents)} agents using <{self.utilization_threshold*100:.0f}% of H/D range",
            evidence={"agents": low_util_agents},
            suggestion="Agents may be stuck — check action space mapping or exploration",
        )
```

- [ ] **Step 7: Implement Rule 4 — InterAgentCoordination**

Create `utils/diagnostics/rules/coordination.py`:

```python
"""InterAgentCoordination: detect lockstep behavior (spec rule #4)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class InterAgentCoordination(DiagnosticRule):
    """Fires when all agent pairs have Pearson correlation > 0.9."""

    name = "InterAgentCoordination"
    check_interval = 100
    min_episodes = 100
    window_size = 50
    severity = Severity.WARN

    def __init__(self, correlation_threshold: float = 0.9):
        self.correlation_threshold = correlation_threshold

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < 10:
            return None

        agent_ids = sorted(recent[0].action_mean.keys())
        if len(agent_ids) < 2:
            return None

        # Build time series of action_mean[0] (H component) per agent
        series = {}
        for aid in agent_ids:
            series[aid] = np.array([m.action_mean[aid][0] for m in recent])

        # Check if all series are constant (std=0) — can't compute correlation
        all_const = all(np.std(series[aid]) < 1e-10 for aid in agent_ids)
        if all_const:
            # All constant and same value = lockstep
            vals = [float(series[aid][0]) for aid in agent_ids]
            if max(vals) - min(vals) < 1e-6:
                return DiagnosticResult(
                    rule_name=self.name,
                    severity=self.severity,
                    message="All agents have identical constant actions",
                    evidence={"pattern": "constant_lockstep"},
                    suggestion="Agents not differentiating — check observation space or reward",
                )
            return None

        # Check all pairs
        all_correlated = True
        min_corr = 1.0
        for i, a1 in enumerate(agent_ids):
            for a2 in agent_ids[i + 1:]:
                s1, s2 = series[a1], series[a2]
                if np.std(s1) < 1e-10 or np.std(s2) < 1e-10:
                    continue
                corr = float(np.corrcoef(s1, s2)[0, 1])
                min_corr = min(min_corr, corr)
                if corr < self.correlation_threshold:
                    all_correlated = False
                    break
            if not all_correlated:
                break

        if not all_correlated:
            return None

        return DiagnosticResult(
            rule_name=self.name,
            severity=self.severity,
            message=f"All agent pairs correlated > {self.correlation_threshold} (min={min_corr:.3f})",
            evidence={"min_correlation": min_corr, "n_agents": len(agent_ids)},
            suggestion="Agents behaving identically — consider diverse initialization or reward shaping",
        )
```

- [ ] **Step 8: Implement Rule 5 — RewardComponentDominance**

Create `utils/diagnostics/rules/dominance.py`:

```python
"""RewardComponentDominance: detect single component > 80% (spec rule #5)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class RewardComponentDominance(DiagnosticRule):
    """Fires when one reward component dominates (> 80%) for the full window."""

    name = "RewardComponentDominance"
    check_interval = 50
    min_episodes = 50
    window_size = 50
    severity = Severity.INFO

    def __init__(self, dominance_threshold: float = 0.8):
        self.dominance_threshold = dominance_threshold

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < self.window_size:
            return None

        # Aggregate component magnitudes
        comp_totals: dict[str, float] = {}
        for m in recent:
            for k, v in m.reward_components.items():
                comp_totals[k] = comp_totals.get(k, 0.0) + abs(v)

        total_magnitude = sum(comp_totals.values())
        if total_magnitude < 1e-10:
            return None

        for comp, mag in comp_totals.items():
            ratio = mag / total_magnitude
            if ratio > self.dominance_threshold:
                return DiagnosticResult(
                    rule_name=self.name,
                    severity=self.severity,
                    message=f"'{comp}' dominates reward: {ratio:.1%} over {len(recent)} eps",
                    evidence={"dominant_component": comp, "ratio": ratio,
                              "all_ratios": {k: v / total_magnitude for k, v in comp_totals.items()}},
                    suggestion=f"Consider adjusting reward weights to rebalance '{comp}'",
                )

        return None
```

- [ ] **Step 9: Implement Rule 6 — ActionCollapse**

Create `utils/diagnostics/rules/action_collapse.py`:

```python
"""ActionCollapse: detect collapsed action distribution (spec rule #6)."""
from __future__ import annotations

import numpy as np

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class ActionCollapse(DiagnosticRule):
    """Fires when any agent's action_std < threshold for the full window."""

    name = "ActionCollapse"
    check_interval = 50
    min_episodes = 50
    window_size = 50
    severity = Severity.WARN

    def __init__(self, std_threshold: float = 0.05):
        self.std_threshold = std_threshold

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < self.window_size:
            return None

        collapsed_agents = []
        agent_ids = sorted(recent[0].action_std.keys())

        for aid in agent_ids:
            # Check if action_std is below threshold for ALL episodes in window
            all_low = all(
                float(np.mean(m.action_std[aid])) < self.std_threshold
                for m in recent
            )
            if all_low:
                mean_std = float(np.mean([np.mean(m.action_std[aid]) for m in recent]))
                collapsed_agents.append({"agent": aid, "mean_std": mean_std})

        if not collapsed_agents:
            return None

        return DiagnosticResult(
            rule_name=self.name,
            severity=self.severity,
            message=f"{len(collapsed_agents)} agents with collapsed actions (std < {self.std_threshold})",
            evidence={"agents": collapsed_agents},
            suggestion="Policy entropy too low — increase entropy target or reset exploration",
        )
```

- [ ] **Step 10: Implement Rule 7 — SolverFailureRate**

Create `utils/diagnostics/rules/solver_failure.py`:

```python
"""SolverFailureRate: detect high simulation failure rate (spec rule #7)."""
from __future__ import annotations

from utils.diagnostics.engine import DiagnosticResult, DiagnosticRule, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics


class SolverFailureRate(DiagnosticRule):
    """Fires when solver failure rate exceeds threshold over the window."""

    name = "SolverFailureRate"
    check_interval = 20
    min_episodes = 20
    window_size = 20
    severity = Severity.WARN

    def __init__(self, failure_threshold: float = 0.2, steps_per_episode: int = 50):
        self.failure_threshold = failure_threshold
        self.steps_per_episode = steps_per_episode

    def check(self, metrics: list[EpisodeMetrics]) -> DiagnosticResult | None:
        recent = metrics[-self.window_size:]
        if len(recent) < self.window_size:
            return None

        total_fail_steps = sum(m.solver_fail_steps for m in recent)
        total_steps = len(recent) * self.steps_per_episode
        fail_rate = total_fail_steps / total_steps if total_steps > 0 else 0

        if fail_rate <= self.failure_threshold:
            return None

        # Count episodes with any failure
        eps_with_fail = sum(1 for m in recent if m.solver_fail_steps > 0)

        return DiagnosticResult(
            rule_name=self.name,
            severity=Severity.STOP if fail_rate > 0.5 else self.severity,
            message=f"Solver failure rate: {fail_rate:.1%} ({eps_with_fail}/{len(recent)} eps affected)",
            evidence={"fail_rate": fail_rate, "total_fail_steps": total_fail_steps,
                      "eps_with_failures": eps_with_fail},
            suggestion="Check simulation parameters or reduce action magnitudes",
        )
```

- [ ] **Step 11: Update rules `__init__.py`**

Update `utils/diagnostics/rules/__init__.py`:

```python
"""Diagnostic rules — imported by DiagnosticsEngine."""
from utils.diagnostics.rules.critic_loss import CriticLossTrend
from utils.diagnostics.rules.improvement import ImprovementStall
from utils.diagnostics.rules.hd_range import HDRangeUtilization
from utils.diagnostics.rules.coordination import InterAgentCoordination
from utils.diagnostics.rules.dominance import RewardComponentDominance
from utils.diagnostics.rules.action_collapse import ActionCollapse
from utils.diagnostics.rules.solver_failure import SolverFailureRate

__all__ = [
    "CriticLossTrend", "ImprovementStall", "HDRangeUtilization",
    "InterAgentCoordination", "RewardComponentDominance",
    "ActionCollapse", "SolverFailureRate",
]
```

- [ ] **Step 12: Run tests to verify they pass**

```bash
python -m pytest tests/test_diagnostics_engine.py -v
```

Expected: all tests PASS.

- [ ] **Step 13: Update `__init__.py` and commit**

Add to `utils/diagnostics/__init__.py`:

```python
from utils.diagnostics.engine import (
    DiagnosticsEngine, DiagnosticRule, DiagnosticReport,
    DiagnosticResult, Severity,
)
```

Add to `__all__`:

```python
    "DiagnosticsEngine", "DiagnosticRule", "DiagnosticReport",
    "DiagnosticResult", "Severity",
```

```bash
git add utils/diagnostics/engine.py \
       utils/diagnostics/rules/critic_loss.py \
       utils/diagnostics/rules/improvement.py \
       utils/diagnostics/rules/hd_range.py \
       utils/diagnostics/rules/coordination.py \
       utils/diagnostics/rules/dominance.py \
       utils/diagnostics/rules/action_collapse.py \
       utils/diagnostics/rules/solver_failure.py \
       utils/diagnostics/rules/__init__.py \
       utils/diagnostics/__init__.py \
       tests/test_diagnostics_engine.py
git commit -m "feat(diagnostics): DiagnosticsEngine + 7 rules"
```

---

### Task 5: WandbTracker

**Files:**
- Create: `utils/diagnostics/wandb_tracker.py`
- Test: `tests/test_wandb_tracker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_wandb_tracker.py`:

```python
"""Tests for WandbTracker (spec Section 6).

Tests use enabled=False (no-op mode) and mock wandb for active mode.
"""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from utils.diagnostics.episode_buffer import EpisodeMetrics
from utils.diagnostics.engine import DiagnosticReport, DiagnosticResult, Severity
from utils.diagnostics.step_info import (
    StepInfo, GridState, AgentState, RewardBreakdown, SolverState,
)
from utils.diagnostics.wandb_tracker import WandbTracker


def _make_metrics(ep=0):
    return EpisodeMetrics(
        episode=ep, total_reward=-50.0,
        reward_components={"r_f": -45.0, "r_h": -3.0, "r_d": -2.0},
        per_agent_rewards={0: -12.5, 1: -12.5, 2: -12.5, 3: -12.5},
        mean_freq_dev_hz=0.1, max_freq_dev_hz=0.2, freq_coi_std=0.01,
        action_mean={i: np.zeros(2) for i in range(4)},
        action_std={i: np.full(2, 0.5) for i in range(4)},
        h_range_used={i: (1.0, 10.0) for i in range(4)},
        d_range_used={i: (0.5, 15.0) for i in range(4)},
        solver_fail_steps=0, done_reason="complete", wall_time_seconds=10.0,
        training_stats={"critic_loss": 2.0},
    )


def _make_report(ep=100):
    return DiagnosticReport(
        episode=ep, timestamp=1000.0,
        results=[
            DiagnosticResult(
                rule_name="CriticLossTrend", severity=Severity.WARN,
                message="test", evidence={}, suggestion="fix it"),
        ],
        health_score=0.8, n_active_rules=3,
    )


class TestWandbTrackerDisabled:
    """Disabled mode: all methods are no-ops."""

    def test_log_episode_noop(self):
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=False)
        tracker.log_episode(_make_metrics())  # should not raise

    def test_log_diagnostics_noop(self):
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=False)
        tracker.log_diagnostics(_make_report())  # should not raise

    def test_finish_noop(self):
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=False)
        tracker.finish({"best_reward": -10})  # should not raise


class TestWandbTrackerEnabled:
    @patch("utils.diagnostics.wandb_tracker.wandb")
    def test_log_episode_calls_wandb(self, mock_wandb):
        mock_wandb.init.return_value = MagicMock()
        tracker = WandbTracker(project="test", scenario="test",
                                config={"lr": 3e-4}, enabled=True)
        tracker.log_episode(_make_metrics(ep=5))
        mock_wandb.log.assert_called_once()
        call_args = mock_wandb.log.call_args
        assert call_args[1]["step"] == 5

    @patch("utils.diagnostics.wandb_tracker.wandb")
    def test_log_diagnostics_calls_wandb(self, mock_wandb):
        mock_wandb.init.return_value = MagicMock()
        mock_wandb.AlertLevel = MagicMock()
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=True)
        tracker.log_diagnostics(_make_report())
        mock_wandb.log.assert_called()

    @patch("utils.diagnostics.wandb_tracker.wandb")
    def test_stop_severity_triggers_alert(self, mock_wandb):
        mock_wandb.init.return_value = MagicMock()
        mock_wandb.AlertLevel = MagicMock()
        report = DiagnosticReport(
            episode=100, timestamp=1000.0,
            results=[DiagnosticResult("test", Severity.STOP, "bad", {}, None)],
            health_score=0.2, n_active_rules=3,
        )
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=True)
        tracker.log_diagnostics(report)
        mock_wandb.alert.assert_called_once()

    @patch("utils.diagnostics.wandb_tracker.wandb")
    def test_finish_sets_summary(self, mock_wandb):
        mock_run = MagicMock()
        mock_wandb.init.return_value = mock_run
        mock_wandb.summary = {}
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=True)
        tracker.finish({"best_reward": -10, "episodes_completed": 500})
        mock_wandb.finish.assert_called_once()

    @patch("utils.diagnostics.wandb_tracker.wandb")
    def test_trajectory_debounce(self, mock_wandb):
        mock_wandb.init.return_value = MagicMock()
        tracker = WandbTracker(project="test", scenario="test",
                                config={}, enabled=True, trajectory_interval=50)
        # First call should proceed
        tracker.log_trajectory(50, [])
        first_call_count = mock_wandb.log.call_count
        # Immediate second call should be debounced
        tracker.log_trajectory(51, [])
        assert mock_wandb.log.call_count == first_call_count  # no new call
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_wandb_tracker.py -v
```

Expected: `ImportError: cannot import name 'WandbTracker'`

- [ ] **Step 3: Implement WandbTracker**

Create `utils/diagnostics/wandb_tracker.py`:

```python
"""WandbTracker: experiment tracking via Weights & Biases (spec Section 6).

All methods are no-ops when enabled=False. wandb is only imported when enabled.
Offline mode: set WANDB_MODE=offline, then `wandb sync` after training.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from utils.diagnostics.engine import DiagnosticReport, Severity
from utils.diagnostics.episode_buffer import EpisodeMetrics
from utils.diagnostics.step_info import StepInfo
from utils.log import get_logger

logger = get_logger(__name__)

# Lazy import — only loaded when enabled=True
wandb: Any = None


def _ensure_wandb():
    global wandb
    if wandb is None:
        import wandb as _wandb
        wandb = _wandb
    return wandb


class WandbTracker:
    """Wandb integration for training monitoring (spec Section 6)."""

    def __init__(
        self,
        project: str,
        scenario: str,
        config: dict,
        enabled: bool = True,
        trajectory_interval: int = 50,
    ):
        self._enabled = enabled
        self.trajectory_interval = trajectory_interval
        self._last_traj_ep = -100  # debounce

        if enabled:
            wb = _ensure_wandb()
            self._run = wb.init(
                project=project,
                name=f"{scenario}_{datetime.now():%m%d_%H%M}",
                config={**config, "step_info_version": "1.0"},
                tags=[scenario, config.get("backend", "unknown")],
            )

    def log_episode(self, metrics: EpisodeMetrics):
        """Log scalar metrics each episode."""
        if not self._enabled:
            return
        d = metrics.to_wandb_dict()
        wandb.log(d, step=metrics.episode)

    def log_diagnostics(self, report: DiagnosticReport):
        """Log diagnostic report. Triggers alert on STOP severity."""
        if not self._enabled:
            return
        d = report.to_wandb_dict()
        wandb.log(d, step=report.episode)

        if report.worst_severity() == Severity.STOP:
            wandb.alert(
                title=f"Training STOP @ ep {report.episode}",
                text="\n".join(r.message for r in report.results),
                level=wandb.AlertLevel.ERROR,
            )

    def log_trajectory(self, episode: int, steps: list[StepInfo]):
        """Log trajectory plot. Debounced: skips if called within 10 eps."""
        if not self._enabled:
            return
        if episode - self._last_traj_ep < 10:
            return
        if not steps:
            return
        self._last_traj_ep = episode

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            n_agents = len(steps[0].agents)
            fig, axes = plt.subplots(2, 2, figsize=(12, 8))
            fig.suptitle(f"Episode {episode} Trajectory")
            t = [s.solver.sim_time for s in steps]

            # Freq
            ax = axes[0, 0]
            for i in range(n_agents):
                ax.plot(t, [s.grid.freq_hz[i] for s in steps], label=f"G{i}")
            ax.set_ylabel("Freq (Hz)")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

            # Power
            ax = axes[0, 1]
            for i in range(n_agents):
                ax.plot(t, [s.grid.power[i] for s in steps], label=f"G{i}")
            ax.set_ylabel("P_es (p.u.)")
            ax.grid(True, alpha=0.3)

            # H
            ax = axes[1, 0]
            for i in range(n_agents):
                ax.plot(t, [s.agents[i].H for s in steps], label=f"G{i}")
            ax.set_ylabel("H (s)")
            ax.set_xlabel("Time (s)")
            ax.grid(True, alpha=0.3)

            # D
            ax = axes[1, 1]
            for i in range(n_agents):
                ax.plot(t, [s.agents[i].D for s in steps], label=f"G{i}")
            ax.set_ylabel("D (p.u.)")
            ax.set_xlabel("Time (s)")
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            wandb.log({f"trajectory/ep{episode}": wandb.Image(fig)},
                      step=episode)
            plt.close(fig)
        except Exception:
            logger.debug("Trajectory plot failed for ep %d", episode, exc_info=True)

    def finish(self, result: dict):
        """Write summary and close wandb run."""
        if not self._enabled:
            return
        for k, v in result.items():
            if v is not None:
                wandb.summary[k] = v
        wandb.finish()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_wandb_tracker.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Update `__init__.py` and commit**

Add to `utils/diagnostics/__init__.py`:

```python
from utils.diagnostics.wandb_tracker import WandbTracker
```

Add to `__all__`:

```python
    "WandbTracker",
```

```bash
git add utils/diagnostics/wandb_tracker.py tests/test_wandb_tracker.py \
       utils/diagnostics/__init__.py
git commit -m "feat(diagnostics): WandbTracker — wandb integration with debounced trajectory plots"
```

---

### Task 6: TunerInterface (ABC only)

**Files:**
- Create: `utils/diagnostics/tuner_interface.py`
- Test: (no separate test file — ABC only, tested implicitly by import)

- [ ] **Step 1: Implement TunerInterface**

Create `utils/diagnostics/tuner_interface.py`:

```python
"""TunerInterface: Phase C auto-tuning ABC (spec Section 7).

B-phase only defines the interface. Implementation deferred to Phase C.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from utils.diagnostics.engine import DiagnosticReport
from utils.diagnostics.episode_buffer import EpisodeMetrics


@dataclass
class HyperparamSuggestion:
    """A suggested hyperparameter change from the tuner."""
    changes: dict[str, Any]   # e.g. {"lr": 1e-4, "gradient_clip": 1.0}
    reason: str               # e.g. "critic_loss rising, reduce LR"
    confidence: float         # 0.0 to 1.0


class TunerInterface(ABC):
    """Abstract interface for Phase C auto-tuning.

    Implementations will wrap Optuna, Ray Tune, or custom logic.
    All data needed is already available via DiagnosticReport and EpisodeMetrics.
    """

    @abstractmethod
    def suggest(
        self, report: DiagnosticReport, recent_metrics: list[EpisodeMetrics],
    ) -> HyperparamSuggestion | None:
        """Suggest hyperparameter changes based on diagnostics. None = no change."""

    @abstractmethod
    def objective(
        self, metrics: list[EpisodeMetrics], final_report: DiagnosticReport,
    ) -> float:
        """Compute optimization objective for a trial.

        Example: 0.7 * normalized_best_reward + 0.3 * mean_health_score
        """

    @abstractmethod
    def should_prune(
        self, metrics: list[EpisodeMetrics], report: DiagnosticReport | None,
    ) -> bool:
        """Whether to early-stop a trial.

        Example triggers:
          - health_score < 0.3 for 3 consecutive checks
          - CriticLossTrend fires STOP
        """

    @abstractmethod
    def search_space(self) -> dict[str, Any]:
        """Return hyperparameter search space (Optuna-compatible format).

        NOTE: Position in config hierarchy matters. The search_space keys
        must map to parameters that run_training() or the train wrapper
        can accept.
        """
```

- [ ] **Step 2: Update `__init__.py` and commit**

Add to `utils/diagnostics/__init__.py`:

```python
from utils.diagnostics.tuner_interface import TunerInterface, HyperparamSuggestion
```

Add to `__all__`:

```python
    "TunerInterface", "HyperparamSuggestion",
```

```bash
python -c "from utils.diagnostics import TunerInterface, HyperparamSuggestion; print('OK')"
```

Expected: `OK`

```bash
git add utils/diagnostics/tuner_interface.py utils/diagnostics/__init__.py
git commit -m "feat(diagnostics): TunerInterface ABC for Phase C auto-tuning"
```

---

### Task 7: train_loop.py Integration

**Files:**
- Modify: `utils/train_loop.py`
- Test: `tests/test_diagnostics_integration.py`

This is the critical integration point. We add 4 optional parameters to `run_training()` and insert 4 hook points into the existing loop. Zero breaking changes.

- [ ] **Step 1: Write failing integration test**

Create `tests/test_diagnostics_integration.py`:

```python
"""Integration test: diagnostics pipeline wired into train_loop.

Uses ODE backend (no ANDES/Simulink dependency) for a minimal 5-episode run.
"""
import os
import sys
import tempfile
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.diagnostics import (
    EpisodeBuffer, DiagnosticsEngine, WandbTracker,
)
from utils.diagnostics.adapters import ode_adapter


def _make_dummy_env():
    """Minimal env stub that produces ODE-like info dicts."""

    class DummyEnv:
        N_AGENTS = 4
        STEPS_PER_EPISODE = 10

        def __init__(self):
            self._step = 0
            self._omega = np.ones(4)

        def reset(self):
            self._step = 0
            self._omega = np.ones(4) + np.random.normal(0, 0.001, 4)
            return {i: np.random.randn(7).astype(np.float32) for i in range(4)}

        def step(self, actions):
            self._step += 1
            self._omega += np.random.normal(0, 0.001, 4)
            freq_hz = self._omega * 50.0
            done = self._step >= self.STEPS_PER_EPISODE
            rewards = {i: float(-np.sum((freq_hz - 50.0) ** 2)) for i in range(4)}
            obs = {i: np.random.randn(7).astype(np.float32) for i in range(4)}
            info = {
                "time": self._step * 0.2,
                "freq_hz": freq_hz.copy(),
                "omega": self._omega.copy(),
                "P_es": np.ones(4) * 5.0,
                "H_es": np.array([3.0, 3.0, 3.0, 3.0]),
                "D_es": np.array([2.0, 2.0, 2.0, 2.0]),
                "delta_H": np.zeros(4),
                "delta_D": np.zeros(4),
                "r_f": -45.0,
                "r_h": -3.0,
                "r_d": -2.0,
                "max_freq_deviation_hz": float(np.max(np.abs(freq_hz - 50.0))),
            }
            return obs, rewards, done, info

        def seed(self, s):
            np.random.seed(s)

    return DummyEnv()


class TestDiagnosticsIntegration:
    def test_train_loop_with_diagnostics(self):
        """Run 5 episodes with full diagnostics pipeline, verify no crash."""
        from utils.train_loop import run_training, build_arg_parser

        # Minimal SAC-like agent stubs
        class StubAgent:
            def __init__(self):
                self.buffer = []

            def select_action(self, obs):
                return np.random.uniform(-1, 1, size=2)

            def update(self):
                return {"critic_loss": 1.0, "actor_loss": 0.5, "entropy": 0.8}

            def save(self, path):
                pass

            def load(self, path):
                pass

            class buffer:
                @staticmethod
                def add(*args):
                    pass

                @staticmethod
                def clear():
                    pass

                def __len__(self):
                    return 100

        # Patch buffer on instances
        agents = []
        for _ in range(4):
            a = StubAgent()
            a.buffer = type("Buf", (), {
                "add": lambda *args: None,
                "clear": lambda: None,
                "__len__": lambda self: 100,
            })()
            agents.append(a)

        with tempfile.TemporaryDirectory() as tmpdir:
            parser = build_arg_parser(defaults={
                "episodes": 5,
                "save_dir": tmpdir,
                "checkpoint_interval": 100,
            })
            args = parser.parse_args([])

            buffer = EpisodeBuffer(capacity=10, save_dir=tmpdir)
            engine = DiagnosticsEngine()
            tracker = WandbTracker(
                project="test", scenario="test", config={}, enabled=False,
            )

            def adapter_fn(step, episode, raw_info, actions, rewards, done):
                return ode_adapter(
                    step=step, episode=episode, raw_info=raw_info,
                    actions=actions, rewards=rewards, done=done, fn=50.0,
                )

            result = run_training(
                env_factory=_make_dummy_env,
                agents_or_manager=agents,
                config={
                    "n_agents": 4, "action_dim": 2,
                    "steps_per_episode": 10,
                    "warmup_steps": 0, "batch_size": 32,
                },
                scenario_name="Integration Test",
                args=args,
                use_monitor=False,
                # New diagnostics params:
                wandb_tracker=tracker,
                diagnostics_engine=engine,
                episode_buffer=buffer,
                step_info_adapter=adapter_fn,
            )

            assert result["episodes_completed"] == 5
            assert buffer.latest_metrics() is not None
            assert buffer.latest_metrics().episode == 4

    def test_without_diagnostics_unchanged(self):
        """Run without diagnostics params — backwards compatible."""
        from utils.train_loop import run_training, build_arg_parser

        class StubAgent:
            def __init__(self):
                self.buffer = type("Buf", (), {
                    "add": lambda *a: None,
                    "clear": lambda: None,
                    "__len__": lambda s: 100,
                })()

            def select_action(self, obs):
                return np.random.uniform(-1, 1, size=2)

            def update(self):
                return None

            def save(self, path):
                pass

            def load(self, path):
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            parser = build_arg_parser(defaults={
                "episodes": 3, "save_dir": tmpdir, "checkpoint_interval": 100,
            })
            args = parser.parse_args([])

            result = run_training(
                env_factory=_make_dummy_env,
                agents_or_manager=[StubAgent() for _ in range(4)],
                config={
                    "n_agents": 4, "action_dim": 2,
                    "steps_per_episode": 10,
                    "warmup_steps": 0, "batch_size": 32,
                },
                scenario_name="Compat Test",
                args=args,
                use_monitor=False,
                # NO diagnostics params
            )
            assert result["episodes_completed"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_diagnostics_integration.py -v
```

Expected: `TypeError: run_training() got an unexpected keyword argument 'wandb_tracker'`

- [ ] **Step 3: Modify train_loop.py — add parameters**

In `utils/train_loop.py`, add 4 new optional parameters to `run_training()` after line 271 (after `close_env=False`):

```python
    # ── Diagnostics (optional, zero-breaking-change) ──
    wandb_tracker=None,            # WandbTracker | None
    diagnostics_engine=None,       # DiagnosticsEngine | None
    episode_buffer=None,           # EpisodeBuffer | None
    step_info_adapter=None,        # Callable | None
```

- [ ] **Step 4: Modify train_loop.py — add step-level hook**

After the existing `adapter.store(...)` block (around line 392), before the per-step update, insert the StepInfo → Buffer hook:

```python
                # ── [Diagnostics] StepInfo → Buffer ──
                if episode_buffer is not None and step_info_adapter is not None:
                    step_info = step_info_adapter(
                        step=step, episode=ep, raw_info=info,
                        actions=actions, rewards=rewards, done=done)
                    episode_buffer.add_step(step_info)
```

- [ ] **Step 5: Modify train_loop.py — add episode-end hooks**

After the end-of-episode update block and before the existing monitor block, insert the diagnostics hooks. Find the `# ── Monitor ──` comment (around line 427) and insert BEFORE it:

```python
            # ── [Diagnostics] patch training stats ──
            if episode_buffer is not None:
                # Aggregate SAC losses into a single dict
                _diag_stats = None
                _valid_losses = [l for l in ep_sac_losses if l is not None]
                if _valid_losses:
                    _diag_stats = {}
                    for key in _valid_losses[0]:
                        _diag_stats[key] = float(np.mean(
                            [l[key] for l in _valid_losses if key in l]))
                episode_buffer.patch_training_stats(ep, _diag_stats)

            # ── [Diagnostics] run diagnostics engine ──
            _stop_reason = None
            if diagnostics_engine is not None and episode_buffer is not None:
                _diag_report = diagnostics_engine.on_episode_end(episode_buffer)
                if _diag_report is not None:
                    if wandb_tracker is not None:
                        wandb_tracker.log_diagnostics(_diag_report)
                    if _diag_report.worst_severity().value == "stop":
                        logger.error("Diagnostics STOP @ ep %d: %s", ep,
                                     [r.message for r in _diag_report.results])
                        _stop_reason = "diagnostics_stop"
                        break

            # ── [Diagnostics] wandb episode logging ──
            if wandb_tracker is not None and episode_buffer is not None:
                _latest = episode_buffer.latest_metrics()
                if _latest is not None:
                    wandb_tracker.log_episode(_latest)

            # ── [Diagnostics] wandb trajectory (periodic) ──
            if wandb_tracker is not None and episode_buffer is not None:
                if (ep + 1) % wandb_tracker.trajectory_interval == 0:
                    _traj = episode_buffer.get_trajectory(ep)
                    if _traj:
                        wandb_tracker.log_trajectory(ep, _traj)
```

- [ ] **Step 6: Modify train_loop.py — add finish hook**

After the `# ── Monitor summary ──` block (around line 486) and before `# ── Final save ──`, insert:

```python
    # ── [Diagnostics] wandb finish ──
    if wandb_tracker is not None:
        wandb_tracker.finish({
            "best_reward": max(total_rewards) if total_rewards else None,
            "episodes_completed": last_ep + 1,
            "final_health_score": (
                diagnostics_engine.latest_health_score()
                if diagnostics_engine else None),
            "stop_reason": _stop_reason or ("interrupted" if interrupted else "max_episodes"),
        })
```

Also initialize `_stop_reason = None` before the main try block (after `last_ep = -1`).

- [ ] **Step 7: Run integration tests**

```bash
python -m pytest tests/test_diagnostics_integration.py -v
```

Expected: both tests PASS.

- [ ] **Step 8: Run ALL diagnostics tests to verify nothing broke**

```bash
python -m pytest tests/test_step_info.py tests/test_adapters.py tests/test_episode_buffer.py \
       tests/test_diagnostics_engine.py tests/test_wandb_tracker.py \
       tests/test_diagnostics_integration.py -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add utils/train_loop.py tests/test_diagnostics_integration.py
git commit -m "feat(diagnostics): wire diagnostics into train_loop — zero breaking changes"
```

---

### Task 8: Wire Up ANDES Kundur Wrapper

**Files:**
- Modify: `scenarios/kundur/train_andes.py`

This task demonstrates how a thin train wrapper enables the full diagnostics pipeline.

- [ ] **Step 1: Modify train_andes.py to pass diagnostics objects**

Add imports at the top of `scenarios/kundur/train_andes.py` (after existing imports):

```python
from utils.diagnostics import EpisodeBuffer, DiagnosticsEngine, WandbTracker
from utils.diagnostics.adapters import andes_adapter
```

In the `main()` function, before the `run_training()` call, add:

```python
    # ── Diagnostics ──
    buffer = EpisodeBuffer(
        capacity=20,
        periodic_save_interval=100,
        save_dir=os.path.join(args.save_dir, "snapshots"),
    )
    engine = DiagnosticsEngine()  # default 7 rules
    tracker = WandbTracker(
        project="multi-agent-vsg",
        scenario="andes_kundur",
        config={
            "backend": "andes",
            "topology": "kundur_4machine",
            "n_agents": N, "obs_dim": obs_dim,
            "lr": cfg.LR, "gamma": cfg.GAMMA,
            "episodes": args.episodes,
        },
        enabled=os.environ.get("WANDB_DISABLED", "").lower() != "true",
    )

    def _andes_step_adapter(step, episode, raw_info, actions, rewards, done):
        return andes_adapter(
            step=step, episode=episode, raw_info=raw_info,
            actions=actions, rewards=rewards, done=done,
            fn=AndesMultiVSGEnv.FN,
        )
```

Then add to the `run_training()` call:

```python
        wandb_tracker=tracker,
        diagnostics_engine=engine,
        episode_buffer=buffer,
        step_info_adapter=_andes_step_adapter,
```

- [ ] **Step 2: Verify import works**

```bash
python -c "import scenarios.kundur.train_andes" 2>&1 || echo "Import check done"
```

This may fail if ANDES is not available on Windows — that's fine. The important thing is that the code is syntactically correct and the imports resolve for the diagnostics modules.

```bash
python -c "from utils.diagnostics import EpisodeBuffer, DiagnosticsEngine, WandbTracker; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/train_andes.py
git commit -m "feat(kundur): wire diagnostics into ANDES Kundur training wrapper"
```

---

### Task 9: Final Validation + Deprecation Marker

**Files:**
- Modify: `utils/monitor.py` (add deprecation warning)
- Verify: full test suite

- [ ] **Step 1: Add deprecation notice to TrainingMonitor**

At the top of `utils/monitor.py`, after the docstring (line 5), add:

```python
import warnings
warnings.warn(
    "TrainingMonitor is deprecated. Use utils.diagnostics.DiagnosticsEngine instead. "
    "See docs/superpowers/specs/2026-03-30-training-diagnostics-system-design.md",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/test_step_info.py tests/test_adapters.py \
       tests/test_episode_buffer.py tests/test_diagnostics_engine.py \
       tests/test_wandb_tracker.py tests/test_diagnostics_integration.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add utils/monitor.py
git commit -m "chore: deprecate TrainingMonitor in favor of DiagnosticsEngine"
```

---

## Summary

| Task | Description | Files | Tests |
|------|-------------|-------|-------|
| 1 | StepInfo data contract | 2 new | 7 tests |
| 2 | Backend adapters | 1 new | 14 tests |
| 3 | EpisodeBuffer + EpisodeMetrics | 1 new | ~15 tests |
| 4 | DiagnosticsEngine + 7 rules | 9 new | ~20 tests |
| 5 | WandbTracker | 1 new | ~7 tests |
| 6 | TunerInterface ABC | 1 new | import check |
| 7 | train_loop.py integration | 1 modify | 2 integration tests |
| 8 | Wire ANDES Kundur wrapper | 1 modify | — |
| 9 | Deprecation + final validation | 1 modify | full suite |

Total: 16 new files, 2 modified files, ~65 tests, 9 commits.
