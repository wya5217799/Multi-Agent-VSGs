# Test Code Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure scattered test files into pytest framework, create unified evaluation pipeline, and optimize paper-style figure generation.

**Architecture:** Three-layer system — `plotting/configs.py` (typed configuration), `plotting/evaluate.py` (data-only evaluation), `plotting/generate_all.py` (figure orchestration). Tests in `tests/` with module-scoped fixtures. Existing `paper_style.py` refactored to return fig objects.

**Tech Stack:** Python, pytest, dataclasses, numpy, matplotlib, ANDES power system simulator

**Spec:** `docs/superpowers/specs/2026-03-24-test-refactor-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `plotting/configs.py` | Create | Typed configuration: EnvType, disturbances, ScenarioConfig, EvalConfig, IOConfig, SCENARIOS, IO_PRESETS |
| `plotting/evaluate.py` | Create | Factory functions (create_env, load_agents), Trajectory/EvalResult dataclasses, run_evaluation, run_robustness_sweep |
| `plotting/generate_all.py` | Create | Orchestration: generate_scenario_figures, main |
| `plotting/paper_style.py` | Modify (lines 165-238, 241-289, 292-384, 387-420) | Remove save params, return fig; add dict→Trajectory compat |
| `env/andes/base_env.py` | Modify (add method ~line 89) | Add `close()` method |
| `tests/__init__.py` | Create | Empty package init |
| `tests/conftest.py` | Create | Module-scoped fixtures: scenario, io_config, env, trained_agents, baseline_reward, normal_rl_reward |
| `tests/test_env.py` | Create | test_reset_succeeds, test_step_no_crash |
| `tests/test_training.py` | Create | test_reward_converges |
| `tests/test_eval.py` | Create | test_rl_beats_baseline, test_freq_within_safe_range |
| `tests/test_robustness.py` | Create | test_comm_failure_degradation, test_comm_delay_degradation |
| `tests/archive/README.md` | Create | Explanation of archived files |
| `pytest.ini` | Create | testpaths, ignore, markers |

---

### Task 1: File Migration — Archive Historical Test Files

**Files:**
- Create: `tests/archive/README.md`
- Move: 11 test files from root → `tests/archive/`
- Create: `pytest.ini`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tests/archive
```

- [ ] **Step 2: Move historical test files to archive**

```bash
git mv test_eval_diag.py tests/archive/
git mv test_eval_rl.py tests/archive/
git mv test_freq_diag.py tests/archive/
git mv test_ne_debug.py tests/archive/
git mv test_ne_debug2.py tests/archive/
git mv test_ne_debug3.py tests/archive/
git mv test_ne_debug4.py tests/archive/
git mv test_ne_debug5.py tests/archive/
git mv test_ne_verify.py tests/archive/
git mv test_regca1_debug.py tests/archive/
git mv test_regca1_verify.py tests/archive/
```

- [ ] **Step 3: Create archive README**

Create `tests/archive/README.md`:
```markdown
# Archived Test Files

Historical debug and verification scripts from development.
These are excluded from pytest runs (see `pytest.ini`).
Kept for reference only — do not add new files here.
```

- [ ] **Step 4: Create pytest.ini**

Create `pytest.ini` at project root:
```ini
[pytest]
testpaths = tests
ignore = tests/archive
markers =
    slow: requires model loading or long simulation
```

- [ ] **Step 5: Create tests/__init__.py**

Create empty `tests/__init__.py`.

- [ ] **Step 6: Verify pytest finds no tests yet**

Run: `python -m pytest tests/ --collect-only`
Expected: "no tests ran" (no test files exist yet in tests/ root)

- [ ] **Step 7: Commit**

```bash
git add tests/ pytest.ini
git commit -m "refactor: archive 11 historical test files, add pytest config"
```

---

### Task 2: Configuration System (`plotting/configs.py`)

**Files:**
- Create: `plotting/configs.py`

- [ ] **Step 1: Create configs.py with all dataclasses and presets**

Create `plotting/configs.py`:
```python
"""
Typed configuration for Multi-Agent VSG evaluation.

Three-layer separation:
  ScenarioConfig — what physical system to simulate
  EvalConfig     — how to run evaluation
  IOConfig       — where to read/write files
"""
from dataclasses import dataclass, field, asdict
from typing import List
from enum import Enum

from env.andes.andes_vsg_env import AndesMultiVSGEnv
from env.andes.andes_ne_env import AndesNEEnv


class EnvType(Enum):
    KUNDUR_VSG = "AndesMultiVSGEnv"
    NEW_ENGLAND = "AndesNEEnv"


# EnvType → concrete class
ENV_CLASS_MAP = {
    EnvType.KUNDUR_VSG: AndesMultiVSGEnv,
    EnvType.NEW_ENGLAND: AndesNEEnv,
}


# ── Disturbance hierarchy ──

@dataclass
class DisturbanceBase:
    name: str
    time: float = 1.0

@dataclass
class LoadStep(DisturbanceBase):
    bus: str = ""
    delta_p: float = 0.0
    delta_q: float = 0.0

@dataclass
class BusFault(DisturbanceBase):
    bus: str = ""
    duration: float = 0.1


# ── Communication config ──

@dataclass
class CommConfig:
    failure_rate: float = 0.0
    delay_steps: int = 0
    topology: str = "full"


# ── Three-layer configs ──

@dataclass
class ScenarioConfig:
    """Physical system description only."""
    name: str
    env_type: EnvType
    n_agents: int
    disturbances: List[DisturbanceBase]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["env_type"] = self.env_type.value
        return d

@dataclass
class EvalConfig:
    """How to run evaluation."""
    deterministic: bool = True
    comm: CommConfig = field(default_factory=CommConfig)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IOConfig:
    """Output paths, determined by evaluation workflow."""
    model_dir: str = ""
    training_log: str = ""
    output_dir: str = "results/figures_paper_style"
    fig_prefix: str = "fig"


# ── Pre-defined scenarios ──

SCENARIOS = {
    "kundur": ScenarioConfig(
        name="kundur",
        env_type=EnvType.KUNDUR_VSG,
        n_agents=4,
        disturbances=[
            LoadStep(name="LS1", bus="BUS6", delta_p=2.0),
            LoadStep(name="LS2", bus="BUS6", delta_p=-2.0),
        ],
    ),
    "new_england": ScenarioConfig(
        name="new_england",
        env_type=EnvType.NEW_ENGLAND,
        n_agents=8,
        disturbances=[
            LoadStep(name="LS1", bus="BUS20", delta_p=3.0),
        ],
    ),
}

IO_PRESETS = {
    "kundur": IOConfig(
        model_dir="results/andes_models_fixed",
        training_log="results/andes_models_fixed/training_log.json",
        fig_prefix="fig",
    ),
    "new_england": IOConfig(
        model_dir="results/andes_ne_models",
        training_log="results/andes_ne_models/training_log.json",
        fig_prefix="fig17",
    ),
}
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from plotting.configs import SCENARIOS, IO_PRESETS, EvalConfig; print('OK:', list(SCENARIOS.keys()))"`
Expected: `OK: ['kundur', 'new_england']`

- [ ] **Step 3: Commit**

```bash
git add plotting/configs.py
git commit -m "feat: add typed configuration system (configs.py)"
```

---

### Task 3: Add `close()` to AndesBaseEnv

**Files:**
- Modify: `env/andes/base_env.py` (~line 89, after `__init__`)

- [ ] **Step 1: Add close method**

Add after `__init__` method (around line 89) in `env/andes/base_env.py`:
```python
    def close(self):
        """Clean up ANDES system resources."""
        self.ss = None
```

- [ ] **Step 2: Verify no import error**

Run: `python -c "from env.andes.andes_vsg_env import AndesMultiVSGEnv; e = AndesMultiVSGEnv(); e.close(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add env/andes/base_env.py
git commit -m "feat: add close() method to AndesBaseEnv"
```

---

### Task 4: Evaluation Layer (`plotting/evaluate.py`)

**Files:**
- Create: `plotting/evaluate.py`

- [ ] **Step 1: Create evaluate.py with data structures and factory functions**

Create `plotting/evaluate.py`:
```python
"""
Unified evaluation pipeline — data only, no plotting.

Produces Trajectory and EvalResult dataclasses consumed by
both tests/ and generate_all.py.
"""
import json
import numpy as np
from dataclasses import dataclass

from plotting.configs import (
    ScenarioConfig, EvalConfig, CommConfig, IOConfig,
    ENV_CLASS_MAP, DisturbanceBase, LoadStep,
)
from agents.sac import SACAgent


# ── Data structures ──

@dataclass
class Trajectory:
    time: np.ndarray
    freq_hz: np.ndarray       # (n_steps, n_agents)
    P_es: np.ndarray          # (n_steps, n_agents)
    M_es: np.ndarray          # (n_steps, n_agents) — raw M=2H from ANDES, NOT H
    D_es: np.ndarray          # (n_steps, n_agents)
    rewards: np.ndarray       # (n_steps,) — sum of per-agent rewards at each step


@dataclass
class EvalResult:
    scenario_name: str
    method: str               # "no_ctrl" / "rl" / "adaptive"
    trajectory: Trajectory
    cumulative_reward: float
    max_freq_dev: float


# ── Factory functions ──

def create_env(scenario: ScenarioConfig, comm: CommConfig = None):
    """Create env instance from ScenarioConfig.

    Note: ANDES env constructors don't take case_path/n_agents as params.
    case_path is hardcoded per class, n_agents is a class constant.
    We only pass comm-related params.
    """
    comm = comm or CommConfig()
    env_cls = ENV_CLASS_MAP[scenario.env_type]
    return env_cls(
        random_disturbance=True,
        comm_fail_prob=comm.failure_rate if comm.failure_rate > 0 else None,
        comm_delay_steps=comm.delay_steps,
    )


def load_agents(model_dir: str, n_agents: int) -> list:
    """Load trained SAC agents from checkpoint directory.

    Kundur uses hidden_sizes=[128,128,128,128] (from plot_andes_eval.py).
    NE uses hidden_sizes=[256,256] (from train script).
    We detect by n_agents.
    """
    import os
    hidden = [128, 128, 128, 128] if n_agents == 4 else [256, 256]
    agents = []
    for i in range(n_agents):
        agent = SACAgent(
            obs_dim=7, action_dim=2, hidden_sizes=hidden,
            buffer_size=10000, batch_size=256,
        )
        path = os.path.join(model_dir, f'agent_{i}_final.pt')
        agent.load(path)
        agents.append(agent)
    return agents


def load_training_log(log_path: str) -> dict:
    """Load training_log.json and return parsed dict."""
    with open(log_path, 'r') as f:
        return json.load(f)


# ── Episode runner ──

def _build_delta_u(disturbance: DisturbanceBase) -> dict:
    """Convert typed DisturbanceBase to env.reset(delta_u=...) format.

    Maps disturbance name to PQ index following plot_andes_eval.py convention:
      LS1 → PQ_0 (load increase), LS2 → PQ_1 (load decrease)
    """
    if isinstance(disturbance, LoadStep):
        # Disturbance name → PQ index mapping
        # From plot_andes_eval.py: LS1={'PQ_0': -2.0}, LS2={'PQ_1': 2.0}
        pq_map = {"LS1": "PQ_0", "LS2": "PQ_1"}
        pq_key = pq_map.get(disturbance.name, "PQ_0")
        return {pq_key: -disturbance.delta_p}
    return {}


def _get_zero_action(env) -> np.ndarray:
    """Compute the normalized action for ΔM=0, ΔD=0."""
    a0 = (0 - env.DM_MIN) / (env.DM_MAX - env.DM_MIN) * 2 - 1
    a1 = (0 - env.DD_MIN) / (env.DD_MAX - env.DD_MIN) * 2 - 1
    return np.array([a0, a1], dtype=np.float32)


def run_evaluation(scenario: ScenarioConfig,
                   disturbance: DisturbanceBase,
                   eval_cfg: EvalConfig,
                   method: str = "rl",
                   env=None,
                   agents=None) -> EvalResult:
    """Run a single evaluation episode. Returns EvalResult.

    Parameters
    ----------
    env : optional, reuse existing env to avoid re-creation
    agents : optional, reuse loaded agents
    """
    _env = env or create_env(scenario, eval_cfg.comm)
    n = scenario.n_agents

    # Reset with specific disturbance
    delta_u = _build_delta_u(disturbance)
    if delta_u:
        _env.random_disturbance = False
        obs = _env.reset(delta_u=delta_u)
    else:
        obs = _env.reset()

    zero_act = _get_zero_action(_env)

    traj_data = {'time': [], 'freq_hz': [], 'P_es': [], 'M_es': [], 'D_es': []}
    rewards_list = []

    for step in range(_env.STEPS_PER_EPISODE):
        if method == "rl" and agents is not None:
            actions = {i: agents[i].select_action(obs[i], deterministic=eval_cfg.deterministic)
                       for i in range(n)}
        else:
            actions = {i: zero_act.copy() for i in range(n)}

        obs, rewards, done, info = _env.step(actions)

        traj_data['time'].append(info['time'])
        traj_data['freq_hz'].append(info['freq_hz'].copy())
        traj_data['P_es'].append(info['P_es'].copy())
        traj_data['M_es'].append(info['M_es'].copy())
        traj_data['D_es'].append(info['D_es'].copy())
        rewards_list.append(sum(rewards.values()) if isinstance(rewards, dict) else float(rewards))

        if done:
            break

    # Convert to arrays
    trajectory = Trajectory(
        time=np.array(traj_data['time']),
        freq_hz=np.array(traj_data['freq_hz']),
        P_es=np.array(traj_data['P_es']),
        M_es=np.array(traj_data['M_es']),
        D_es=np.array(traj_data['D_es']),
        rewards=np.array(rewards_list),
    )

    return EvalResult(
        scenario_name=scenario.name,
        method=method,
        trajectory=trajectory,
        cumulative_reward=float(np.sum(trajectory.rewards)),
        max_freq_dev=float(np.max(np.abs(trajectory.freq_hz - 50.0))),
    )


def run_robustness_sweep(scenario: ScenarioConfig,
                         disturbance: DisturbanceBase,
                         eval_cfg: EvalConfig,
                         env=None, agents=None,
                         failure_rates=None,
                         delay_steps_list=None) -> dict:
    """Parameter sweep for robustness evaluation.

    Returns dict of {param_label: EvalResult}.
    Note: creates new envs per comm config (comm params are set at construction).
    """
    from dataclasses import replace
    results = {}

    for rate in (failure_rates or []):
        cfg = replace(eval_cfg, comm=CommConfig(failure_rate=rate))
        sweep_env = create_env(scenario, cfg.comm)
        sweep_agents = agents  # reuse agents
        results[f"fail_{rate}"] = run_evaluation(
            scenario, disturbance, cfg, method="rl",
            env=sweep_env, agents=sweep_agents,
        )
        sweep_env.close()

    for delay in (delay_steps_list or []):
        cfg = replace(eval_cfg, comm=CommConfig(delay_steps=delay))
        sweep_env = create_env(scenario, cfg.comm)
        results[f"delay_{delay}"] = run_evaluation(
            scenario, disturbance, cfg, method="rl",
            env=sweep_env, agents=agents,
        )
        sweep_env.close()

    return results
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from plotting.evaluate import Trajectory, EvalResult, create_env, load_agents; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plotting/evaluate.py
git commit -m "feat: add unified evaluation pipeline (evaluate.py)"
```

---

### Task 5: Refactor paper_style.py — Return fig, Accept Trajectory

**Files:**
- Modify: `plotting/paper_style.py` (lines 165-238, 241-289, 292-384, 387-420)

- [ ] **Step 1: Refactor `plot_time_domain_2x2` — remove save params, return fig, add Trajectory compat**

In `plotting/paper_style.py`, change the function signature and body at line 165-238.

Old signature (line 165-166):
```python
def plot_time_domain_2x2(traj, fig_label, save_name, save_dir,
                          n_agents=4, f_nom=50.0):
```

New signature:
```python
def plot_time_domain_2x2(traj, n_agents=4, f_nom=50.0, fig_label=''):
```

At the start of the function body (after docstring), add Trajectory compat:
```python
    # Accept both dict and Trajectory dataclass
    if hasattr(traj, 'time'):
        _t = traj
    else:
        from plotting.evaluate import Trajectory
        _t = type('_T', (), traj)()  # duck-type dict as object
    # Use _t.time, _t.freq_hz etc. below — but for backward compat,
    # just keep using traj[key] if dict, traj.key if object
```

Actually, simpler approach — normalize to dict access since the plotting code already uses dict:
```python
    if not isinstance(traj, dict):
        # Convert Trajectory dataclass to dict for internal use
        traj = {
            'time': traj.time, 'freq_hz': traj.freq_hz,
            'P_es': traj.P_es, 'M_es': traj.M_es, 'D_es': traj.D_es,
        }
```

Remove the `save_fig(fig, save_dir, save_name)` call at line 238.
Add `return fig` instead.

- [ ] **Step 2: Refactor `plot_cumulative_reward` — remove save params, return fig**

Old signature (line 241):
```python
def plot_cumulative_reward(rewards_dict, save_name, save_dir, fig_label='(a)'):
```

New signature:
```python
def plot_cumulative_reward(rewards_dict, fig_label='(a)'):
```

Remove `save_fig(fig, save_dir, save_name)` at line 289.
Add `return fig`.

- [ ] **Step 3: Refactor `plot_training_curves` — remove save params, return fig**

Old signature (line 292):
```python
def plot_training_curves(total_rewards, agent_rewards, save_name, save_dir,
                          freq_rewards=None, inertia_rewards=None,
                          droop_rewards=None, n_agents=4, window=50):
```

New signature:
```python
def plot_training_curves(total_rewards, agent_rewards,
                          freq_rewards=None, inertia_rewards=None,
                          droop_rewards=None, n_agents=4, window=50):
```

Remove `save_fig(fig, save_dir, save_name)` at line 384.
Add `return fig`.

- [ ] **Step 4: Refactor `plot_freq_comparison` — remove save params, return fig, add Trajectory compat**

Old signature (line 387):
```python
def plot_freq_comparison(trajs_dict, save_name, save_dir,
                          agent_idx=0, f_nom=50.0):
```

New signature:
```python
def plot_freq_comparison(trajs_dict, agent_idx=0, f_nom=50.0):
```

At function start, normalize Trajectory to dict:
```python
    _trajs = {}
    for label, traj in trajs_dict.items():
        if not isinstance(traj, dict):
            traj = {'time': traj.time, 'freq_hz': traj.freq_hz}
        _trajs[label] = traj
    trajs_dict = _trajs
```

Remove `save_fig(fig, save_dir, save_name)` at line 420.
Add `return fig`.

- [ ] **Step 5: Verify paper_style imports still work**

Run: `python -c "from plotting.paper_style import plot_time_domain_2x2, plot_cumulative_reward, plot_training_curves; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add plotting/paper_style.py
git commit -m "refactor: paper_style functions return fig, remove internal save"
```

---

### Task 6: Update Existing Callers of paper_style

**Files:**
- Modify: `plotting/plot_andes_eval.py` (lines 100-107, 126, 143-147, 152-153, 165-168, 174-175)
- Modify: `plotting/plot_andes_fig4.py`

These existing scripts call the old signatures. Update them to pass only the new params and call `save_fig()` separately.

- [ ] **Step 1: Update plot_andes_eval.py — all call sites**

Every call like:
```python
plot_time_domain_2x2(traj, 'Fig6-', 'fig6.png', SAVE_DIR, n_agents=N)
```
becomes:
```python
fig = plot_time_domain_2x2(traj, n_agents=N, fig_label='Fig6-')
save_fig(fig, SAVE_DIR, 'fig6.png')
```

Every call like:
```python
plot_cumulative_reward(results, 'fig5.png', SAVE_DIR)
```
becomes:
```python
fig = plot_cumulative_reward(results)
save_fig(fig, SAVE_DIR, 'fig5.png')
```

Update import to include `save_fig`:
```python
from plotting.paper_style import (
    plot_time_domain_2x2, plot_cumulative_reward, compute_freq_sync_reward, save_fig
)
```

- [ ] **Step 2: Update plot_andes_fig4.py — call site**

Same pattern: add `save_fig` import, capture return, call save_fig separately.

- [ ] **Step 3: Verify plot_andes_eval.py runs without error (dry run)**

Run: `python -c "import plotting.plot_andes_eval; print('Import OK')"`
Expected: `Import OK` (just check imports, don't run main)

- [ ] **Step 4: Commit**

```bash
git add plotting/plot_andes_eval.py plotting/plot_andes_fig4.py
git commit -m "refactor: update existing callers to new paper_style API"
```

---

### Task 7: Figure Generation Orchestrator (`plotting/generate_all.py`)

**Files:**
- Create: `plotting/generate_all.py`

- [ ] **Step 1: Create generate_all.py**

Create `plotting/generate_all.py`:
```python
"""
One-click paper figure generation.

Usage:
    python -m plotting.generate_all                # all scenarios
    python -m plotting.generate_all kundur         # single scenario
"""
import sys
import numpy as np

from plotting.configs import SCENARIOS, IO_PRESETS, EvalConfig
from plotting.evaluate import (
    create_env, load_agents, load_training_log,
    run_evaluation, run_robustness_sweep,
)
from plotting.paper_style import (
    apply_ieee_style, plot_training_curves, plot_time_domain_2x2,
    plot_cumulative_reward, save_fig,
)


def generate_scenario_figures(scenario_name: str):
    """Generate all paper figures for one scenario."""
    scenario = SCENARIOS[scenario_name]
    io = IO_PRESETS[scenario_name]
    eval_cfg = EvalConfig()
    apply_ieee_style()

    print(f'\n{"="*60}')
    print(f' Generating figures: {scenario_name}')
    print(f'{"="*60}')

    # Cache env and agents for entire scenario
    env = create_env(scenario)
    agents = load_agents(io.model_dir, scenario.n_agents)

    # 1. Training curves
    print('\n--- Training curves ---')
    log = load_training_log(io.training_log)
    fig = plot_training_curves(
        np.array(log["total_rewards"]),
        [np.array(a) for a in log.get("agent_rewards", [])],
    )
    save_fig(fig, io.output_dir, f"{io.fig_prefix}_training.png")

    # 2. Per-disturbance: no-control + RL time-domain plots
    all_results = {}
    for dist in scenario.disturbances:
        print(f'\n--- {dist.name} ---')
        no_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="no_ctrl", env=env)
        rl_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="rl", env=env, agents=agents)
        all_results[dist.name] = {"no_ctrl": no_ctrl, "rl": rl_ctrl}

        fig = plot_time_domain_2x2(no_ctrl.trajectory, n_agents=scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_no_ctrl.png")

        fig = plot_time_domain_2x2(rl_ctrl.trajectory, n_agents=scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_ctrl.png")

    # 3. Cumulative reward per disturbance
    for dist_name, results in all_results.items():
        print(f'\n--- Cumulative reward: {dist_name} ---')
        fig = plot_cumulative_reward(
            {k: v.trajectory.rewards.tolist() for k, v in results.items()}
        )
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist_name}_cumulative.png")

    # 4. Robustness sweep
    print('\n--- Robustness sweep ---')
    first_dist = scenario.disturbances[0]
    robustness = run_robustness_sweep(
        scenario, first_dist, eval_cfg, agents=agents,
        failure_rates=[0.1, 0.2, 0.3],
        delay_steps_list=[1, 2, 3],
    )
    for label, result in robustness.items():
        print(f'  {label}: cumulative_reward={result.cumulative_reward:.2f}')

    env.close()
    print(f'\nAll figures saved to {io.output_dir}')


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(SCENARIOS.keys())
    for name in targets:
        if name not in SCENARIOS:
            print(f'Unknown scenario: {name}')
            continue
        if name not in IO_PRESETS:
            print(f'No IO preset for {name}, skipping')
            continue
        generate_scenario_figures(name)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import**

Run: `python -c "from plotting.generate_all import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plotting/generate_all.py
git commit -m "feat: add one-click figure generation (generate_all.py)"
```

---

### Task 8: pytest Fixtures (`tests/conftest.py`)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create conftest.py**

Create `tests/conftest.py`:
```python
"""Shared pytest fixtures for Multi-Agent VSG tests."""
import pytest
import numpy as np

from plotting.configs import SCENARIOS, IO_PRESETS, CommConfig
from plotting.evaluate import create_env, load_agents


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: requires model loading or long simulation")


@pytest.fixture(scope="module", params=list(SCENARIOS.keys()))
def scenario(request):
    """Parametrized scenario — auto-runs all SCENARIOS entries."""
    return SCENARIOS[request.param]


@pytest.fixture(scope="module")
def io_config(scenario):
    if scenario.name not in IO_PRESETS:
        pytest.skip(f"No IO config for {scenario.name}")
    return IO_PRESETS[scenario.name]


@pytest.fixture(scope="module")
def env(scenario):
    """Create ANDES env, auto-cleanup after module."""
    _env = create_env(scenario)
    yield _env
    _env.close()


@pytest.fixture(scope="module")
def trained_agents(scenario, io_config):
    """Load trained SAC agents."""
    return load_agents(io_config.model_dir, scenario.n_agents)


@pytest.fixture(scope="module")
def baseline_reward(env, scenario):
    """No-control baseline cumulative reward, run once per module."""
    from plotting.evaluate import _get_zero_action
    env.reset()
    total = 0.0
    zero_act = _get_zero_action(env)
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: zero_act.copy() for i in range(scenario.n_agents)}
        _, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    return total


@pytest.fixture(scope="module")
def normal_rl_reward(env, scenario, trained_agents):
    """Normal-comm RL cumulative reward, shared by eval and robustness tests."""
    total = 0.0
    obs = env.reset()
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    return total
```

- [ ] **Step 2: Verify fixtures are collected**

Run: `python -m pytest tests/ --collect-only`
Expected: Shows conftest.py loaded, no errors

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "feat: add pytest fixtures (conftest.py)"
```

---

### Task 9: test_env.py — Environment Correctness

**Files:**
- Create: `tests/test_env.py`

- [ ] **Step 1: Create test_env.py**

Create `tests/test_env.py`:
```python
"""Environment correctness tests — fast, run daily."""


def test_reset_succeeds(env):
    """env.reset() returns valid observation, TDS not busted."""
    obs = env.reset()
    assert obs is not None
    assert not env.ss.TDS.busted


def test_step_no_crash(env, scenario):
    """50 zero-action steps without TDS failure."""
    from plotting.evaluate import _get_zero_action
    env.reset()
    zero_act = _get_zero_action(env)
    for step in range(50):
        actions = {i: zero_act.copy() for i in range(scenario.n_agents)}
        obs, rewards, done, info = env.step(actions)
        assert not info.get("tds_failed", False), f"TDS failed at step {step}"
        if done:
            break
```

- [ ] **Step 2: Run test_env.py**

Run: `python -m pytest tests/test_env.py -v`
Expected: 2 tests per scenario (4 total), all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_env.py
git commit -m "feat: add environment correctness tests"
```

---

### Task 10: test_training.py — Training Convergence

**Files:**
- Create: `tests/test_training.py`

- [ ] **Step 1: Create test_training.py**

Create `tests/test_training.py`:
```python
"""Training convergence tests — fast, reads log files only."""
import numpy as np
from plotting.evaluate import load_training_log


def test_reward_converges(io_config):
    """Training rewards improve >20% from early to late, and late-stage > threshold."""
    log = load_training_log(io_config.training_log)
    rewards = np.array(log["total_rewards"])
    early = np.mean(rewards[:50])
    late = np.mean(rewards[-50:])
    improvement = (late - early) / (abs(early) + 1e-8)
    assert improvement > 0.2, f"Improvement insufficient: {improvement:.1%}"
    assert late > -50, f"Late-stage reward too low: {late:.2f}"
```

- [ ] **Step 2: Run test_training.py**

Run: `python -m pytest tests/test_training.py -v`
Expected: 1 test per scenario (2 total), all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_training.py
git commit -m "feat: add training convergence tests"
```

---

### Task 11: test_eval.py — Control Effectiveness

**Files:**
- Create: `tests/test_eval.py`

- [ ] **Step 1: Create test_eval.py**

Create `tests/test_eval.py`:
```python
"""Control effectiveness tests — slow, requires model loading."""
import pytest


@pytest.mark.slow
def test_rl_beats_baseline(env, scenario, trained_agents, baseline_reward):
    """RL control cumulative reward significantly exceeds no-control baseline."""
    env.reset()
    total = 0.0
    obs = env.reset()
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    # For negative rewards (penalty-based), less negative = better.
    # Check RL is significantly better (closer to 0) than baseline.
    assert total > baseline_reward, (
        f"RL reward {total:.2f} not better than baseline {baseline_reward:.2f}"
    )
    # Also check meaningful improvement (at least 20% reduction in penalty)
    improvement = (total - baseline_reward) / (abs(baseline_reward) + 1e-8)
    assert improvement > 0.2, (
        f"RL improvement insufficient: {improvement:.1%} (RL={total:.2f}, baseline={baseline_reward:.2f})"
    )


@pytest.mark.slow
def test_freq_within_safe_range(env, scenario, trained_agents):
    """Frequency deviation stays within safe range under RL control."""
    obs = env.reset()
    max_dev = 0.0
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, info = env.step(actions)
        freq_dev = abs(info.get('freq_hz', [50.0]) - 50.0)
        if hasattr(freq_dev, 'max'):
            max_dev = max(max_dev, float(freq_dev.max()))
        if done:
            break
    assert max_dev < 1.0, f"Max frequency deviation too large: {max_dev:.3f} Hz"
```

- [ ] **Step 2: Run test_eval.py**

Run: `python -m pytest tests/test_eval.py -v`
Expected: 2 tests per scenario (4 total), all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_eval.py
git commit -m "feat: add control effectiveness tests"
```

---

### Task 12: test_robustness.py — Communication Robustness

**Files:**
- Create: `tests/test_robustness.py`

- [ ] **Step 1: Create test_robustness.py**

Create `tests/test_robustness.py`:
```python
"""Communication robustness tests — slow, parametrized sweeps."""
import pytest
from plotting.configs import CommConfig
from plotting.evaluate import create_env, _get_zero_action


@pytest.mark.slow
@pytest.mark.parametrize("failure_rate", [0.1, 0.3, 0.5])
def test_comm_failure_degradation(scenario, trained_agents,
                                   normal_rl_reward, failure_rate):
    """Performance degradation under communication failure stays < 30%."""
    comm = CommConfig(failure_rate=failure_rate)
    env = create_env(scenario, comm)
    obs = env.reset()
    total = 0.0
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    env.close()

    # For negative rewards: degradation = how much worse (more negative) vs normal
    degradation = (normal_rl_reward - total) / (abs(normal_rl_reward) + 1e-8)
    assert degradation < 0.3, (
        f"rate={failure_rate}: degradation {degradation:.1%} exceeds 30%"
    )


@pytest.mark.slow
@pytest.mark.parametrize("delay_steps", [1, 2, 3])
def test_comm_delay_degradation(scenario, trained_agents,
                                 normal_rl_reward, delay_steps):
    """Performance degradation under communication delay stays < 30%."""
    comm = CommConfig(delay_steps=delay_steps)
    env = create_env(scenario, comm)
    obs = env.reset()
    total = 0.0
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    env.close()

    # For negative rewards: degradation = how much worse (more negative) vs normal
    degradation = (normal_rl_reward - total) / (abs(normal_rl_reward) + 1e-8)
    assert degradation < 0.3, (
        f"delay={delay_steps}: degradation {degradation:.1%} exceeds 30%"
    )
```

- [ ] **Step 2: Run test_robustness.py**

Run: `python -m pytest tests/test_robustness.py -v`
Expected: 6 tests per scenario (12 total), all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_robustness.py
git commit -m "feat: add communication robustness tests"
```

---

### Task 13: Full Integration Verification

- [ ] **Step 1: Run all fast tests**

Run: `python -m pytest tests/ -v -m "not slow"`
Expected: test_env + test_training tests pass

- [ ] **Step 2: Run all tests including slow**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Run single-scenario filter**

Run: `python -m pytest tests/ -v -k "kundur"`
Expected: Only kundur-parametrized tests run

- [ ] **Step 4: Verify generate_all.py dry import**

Run: `python -c "from plotting.generate_all import generate_scenario_figures; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration test fixes"
```
