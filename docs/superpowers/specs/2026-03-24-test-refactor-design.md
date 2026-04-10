# Test Code Refactoring Design — Multi-Agent VSGs

**Date:** 2026-03-24
**Status:** Reviewed (R1 fixes applied)
**Scope:** Restructure test code, unify evaluation pipeline, optimize paper-style figure generation

## 1. Goals

- Consolidate 11 scattered root-level test files into a structured pytest framework
- Create a unified evaluation pipeline for all scenarios (Kundur 4-bus, New England 39-bus)
- Enable one-command paper figure generation with consistent IEEE styling
- Maintain backward compatibility with existing paper_style.py plotting code

## 2. Directory Structure

```
Multi-Agent VSGs/
├── plotting/
│   ├── configs.py           # NEW: scenario/eval/IO configuration (dataclass)
│   ├── evaluate.py          # NEW: unified evaluation entry (data only, no plotting)
│   ├── generate_all.py      # NEW: one-click figure generation
│   ├── paper_style.py       # MODIFY: dict → Trajectory adapter
│   ├── plot_andes_eval.py   # KEEP (transitional)
│   ├── plot_andes_fig4.py   # KEEP (transitional)
│   └── ...                  # other existing scripts unchanged
├── tests/
│   ├── archive/             # NEW: historical debug files
│   │   ├── README.md
│   │   └── test_*.py (11 files)
│   ├── conftest.py          # NEW: shared fixtures
│   ├── test_env.py          # NEW: environment correctness
│   ├── test_training.py     # NEW: training convergence
│   ├── test_eval.py         # NEW: control effectiveness
│   └── test_robustness.py   # NEW: communication robustness
├── pytest.ini               # NEW: test configuration
└── ...
```

## 3. Configuration System (`plotting/configs.py`)

Three-layer separation: what to simulate / how to evaluate / where to save.

### 3.1 Environment Type Enum

```python
from enum import Enum

from env.andes.andes_vsg_env import AndesMultiVSGEnv
from env.andes.andes_ne_env import AndesNEEnv

class EnvType(Enum):
    KUNDUR_VSG = "AndesMultiVSGEnv"    # actual class name
    NEW_ENGLAND = "AndesNEEnv"

# Direct class mapping for factory function
ENV_CLASS_MAP = {
    EnvType.KUNDUR_VSG: AndesMultiVSGEnv,
    EnvType.NEW_ENGLAND: AndesNEEnv,
}
```

### 3.2 Disturbance Type Hierarchy

```python
from dataclasses import dataclass

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
```

### 3.3 Communication Config (independent, supports sweep)

```python
@dataclass
class CommConfig:
    failure_rate: float = 0.0
    delay_steps: int = 0
    topology: str = "full"
```

### 3.4 Scenario / Eval / IO Configs

```python
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class ScenarioConfig:
    """Physical system description only"""
    name: str
    env_type: EnvType
    case_path: str
    n_agents: int
    disturbances: List[DisturbanceBase]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["env_type"] = self.env_type.value
        return d

@dataclass
class EvalConfig:
    """How to run evaluation"""
    n_episodes: int = 20
    deterministic: bool = True
    comm: CommConfig = field(default_factory=CommConfig)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IOConfig:
    """Output paths, determined by evaluation workflow"""
    model_dir: str = ""
    training_log: str = ""
    output_dir: str = "results/figures_paper_style"
    fig_prefix: str = "fig"
```

### 3.5 Pre-defined Scenarios and IO Presets

```python
SCENARIOS = {
    "kundur": ScenarioConfig(
        name="kundur",
        env_type=EnvType.KUNDUR_VSG,
        case_path="kundur/kundur_full.xlsx",          # andes.get_case() path
        n_agents=4,
        disturbances=[
            LoadStep(name="LS1", bus="BUS6", delta_p=2.0),
            LoadStep(name="LS2", bus="BUS6", delta_p=-2.0),
        ],
    ),
    "new_england": ScenarioConfig(
        name="new_england",
        env_type=EnvType.NEW_ENGLAND,
        case_path="ieee39/ieee39_full.xlsx",            # andes.get_case() path
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

## 4. Evaluation Layer (`plotting/evaluate.py`)

Data-only evaluation — produces structured results, no plotting.

### 4.1 Data Structures

```python
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
```

### 4.2 Core Functions

```python
def create_env(scenario: ScenarioConfig):
    """Factory: creates env instance from ScenarioConfig.
    Uses ENV_CLASS_MAP to resolve EnvType → concrete class.
    Calls andes.get_case(scenario.case_path) for ANDES case loading."""
    from plotting.configs import ENV_CLASS_MAP
    env_cls = ENV_CLASS_MAP[scenario.env_type]
    return env_cls(case_path=scenario.case_path, n_agents=scenario.n_agents)

def load_agents(model_dir: str, n_agents: int) -> list:
    """Load trained SAC agents from checkpoint directory.
    Agent hyperparams (obs_dim=7, action_dim=2, hidden_sizes=[256,256])
    are fixed per the paper's architecture. Each agent loaded from
    {model_dir}/agent_{i}_final.pt."""
    from agents.sac import SACAgent
    agents = []
    for i in range(n_agents):
        agent = SACAgent(obs_dim=7, action_dim=2, hidden_sizes=[256, 256])
        agent.load(f"{model_dir}/agent_{i}_final.pt")
        agents.append(agent)
    return agents

def run_evaluation(scenario: ScenarioConfig,
                   disturbance: DisturbanceBase,
                   eval_cfg: EvalConfig,
                   method: str = "rl",
                   env=None,
                   agents=None) -> EvalResult:
    """Single evaluation run. Accepts optional env/agents to avoid re-creation."""
    _env = env or create_env(scenario)
    _agents = agents or (load_agents(...) if method == "rl" else None)
    trajectory = _run_episode(_env, _agents, disturbance, eval_cfg, method)
    return EvalResult(...)

def run_robustness_sweep(scenario, eval_cfg,
                         env=None, agents=None,
                         failure_rates=None,
                         delay_steps_list=None) -> dict:
    """Parameter sweep for robustness evaluation.
    Uses dataclasses.replace to preserve caller's eval_cfg settings."""
    from dataclasses import replace
    results = {}
    for rate in (failure_rates or []):
        cfg = replace(eval_cfg, comm=CommConfig(failure_rate=rate))
        results[f"fail_{rate}"] = run_evaluation(scenario, ..., cfg, env=env, agents=agents)
    for delay in (delay_steps_list or []):
        cfg = replace(eval_cfg, comm=CommConfig(delay_steps=delay))
        results[f"delay_{delay}"] = run_evaluation(scenario, ..., cfg, env=env, agents=agents)
    return results
```

## 5. Figure Generation (`plotting/generate_all.py`)

Thin orchestration layer — connects evaluation data to plotting functions.

```python
def generate_scenario_figures(scenario_name: str):
    scenario = SCENARIOS[scenario_name]
    io = IO_PRESETS[scenario_name]
    eval_cfg = EvalConfig()
    apply_ieee_style()

    # Cache env and agents for entire scenario
    env = create_env(scenario)
    agents = load_agents(io.model_dir, scenario.n_agents)

    # 1. Training curves
    log = load_training_log(io.training_log)
    fig = plot_training_curves(log["total_rewards"], log["agent_rewards"])
    save_fig(fig, io.output_dir, f"{io.fig_prefix}_training")

    # 2. Per-disturbance: collect all results
    all_results = {}
    for dist in scenario.disturbances:
        no_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="no_ctrl", env=env)
        rl_ctrl = run_evaluation(scenario, dist, eval_cfg,
                                 method="rl", env=env, agents=agents)
        all_results[dist.name] = {"no_ctrl": no_ctrl, "rl": rl_ctrl}

        fig = plot_time_domain_2x2(no_ctrl.trajectory, scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_no_ctrl")
        fig = plot_time_domain_2x2(rl_ctrl.trajectory, scenario.n_agents)
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist.name}_ctrl")

    # 3. Cumulative reward per disturbance
    for dist_name, results in all_results.items():
        fig = plot_cumulative_reward(
            {k: v.trajectory.rewards for k, v in results.items()}
        )
        save_fig(fig, io.output_dir, f"{io.fig_prefix}_{dist_name}_cumulative")

    # 4. Robustness sweep (reuse env and agents)
    robustness = run_robustness_sweep(
        scenario, eval_cfg, env=env, agents=agents,
        failure_rates=[0.1, 0.2, 0.3],
        delay_steps_list=[1, 2, 3],
    )

    env.close()

def main():
    for name in SCENARIOS:
        if name in IO_PRESETS:
            generate_scenario_figures(name)
```

## 6. paper_style.py Changes

**Strategy:** Preserve all plotting logic. Two breaking changes required to decouple
plotting from file I/O, enabling reuse by both generate_all.py and tests.

### 6.1 Breaking Change: Functions Return `fig` Instead of Saving Internally

Currently `plot_time_domain_2x2()` and `plot_cumulative_reward()` call `save_fig()`
internally using `save_name`/`save_dir` parameters. This couples plotting to file output.

**Change:** Remove `save_name`/`save_dir`/`fig_label` params, return `fig` object.
Callers use `save_fig(fig, ...)` separately.

```python
# BEFORE (current):
def plot_time_domain_2x2(traj, fig_label, save_name, save_dir, n_agents=4, f_nom=50.0):
    ...
    save_fig(fig, save_dir, save_name)  # saves internally

# AFTER (new):
def plot_time_domain_2x2(traj, n_agents=4, f_nom=50.0) -> Figure:
    ...
    return fig  # caller decides where/whether to save
```

Same pattern for `plot_cumulative_reward()` and `plot_freq_comparison()`.

### 6.2 Input Type: dict → Trajectory

| Function | Change | Reason |
|----------|--------|--------|
| `plot_time_domain_2x2()` | Remove save params, return fig; `dict` → `Trajectory` | Decouple I/O + type safety |
| `plot_cumulative_reward()` | Remove save params, return fig | Decouple I/O |
| `plot_training_curves()` | No change | Already returns fig |
| `plot_freq_comparison()` | `dict` → `dict[str, Trajectory]`, return fig | Consistency |
| `save_fig()` | No change | Already supports output_dir |
| `apply_ieee_style()` | No change | Global config |

### 6.3 Backward Compatibility (transitional)

During transition, accept both dict and Trajectory:

```python
def plot_time_domain_2x2(traj, n_agents: int = 4, f_nom: float = 50.0) -> Figure:
    if isinstance(traj, dict):
        traj = Trajectory(**traj)  # auto-convert legacy dict
    time = traj.time
    freq = traj.freq_hz
    ...
    return fig
```

Remove compatibility layer after all old scripts migrate to generate_all.py.

## 7. pytest Test Layer (`tests/`)

### 7.1 Configuration (`pytest.ini`)

```ini
[pytest]
testpaths = tests
ignore = tests/archive
markers =
    slow: requires model loading or long simulation
```

### 7.2 Shared Fixtures (`tests/conftest.py`)

```python
import pytest
import numpy as np
from plotting.configs import SCENARIOS, IO_PRESETS, CommConfig

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: requires model loading or long simulation")

# All fixtures use scope="module" to avoid ScopeMismatch errors
# and to avoid re-creating expensive ANDES environments per test function.

@pytest.fixture(scope="module", params=list(SCENARIOS.keys()))
def scenario(request):
    return SCENARIOS[request.param]

@pytest.fixture(scope="module")
def io_config(scenario):
    if scenario.name not in IO_PRESETS:
        pytest.skip(f"No IO config for {scenario.name}")
    return IO_PRESETS[scenario.name]

@pytest.fixture(scope="module")
def env(scenario):
    env = create_env(scenario)
    yield env
    if hasattr(env, 'close'):
        env.close()

@pytest.fixture(scope="module")
def trained_agents(scenario, io_config):
    return load_agents(io_config.model_dir, scenario.n_agents)

@pytest.fixture(scope="module")
def baseline_reward(env, scenario):
    """No-control baseline, run once per module"""
    env.reset()
    total = 0.0
    zero_action = [0.0] * (2 * scenario.n_agents)
    done = False
    while not done:
        _, r, done, _ = env.step(zero_action)
        total += r
    return total

@pytest.fixture(scope="module")
def normal_rl_reward(env, scenario, trained_agents):
    """Normal-comm RL performance, shared by eval and robustness"""
    env.reset()
    total = 0.0
    done = False
    while not done:
        obs = env.get_obs()
        actions = [a.select_action(obs[i], deterministic=True)
                   for i, a in enumerate(trained_agents)]
        _, r, done, _ = env.step(actions)
        total += r
    return total
```

### 7.3 Test Files

**test_env.py** — Fast, daily development:
- `test_reset_succeeds`: env.reset() returns valid obs, TDS not busted
- `test_step_no_crash`: 50 zero-action steps without tds_failed

**test_training.py** — Fast, reads log files only:
- `test_reward_converges`: improvement > 20%, late-stage reward > threshold

**test_eval.py** — Slow, requires model loading:
- `test_rl_beats_baseline`: RL cumulative reward > baseline * 1.2
- `test_freq_within_safe_range`: max frequency deviation < 1.0 Hz

**test_robustness.py** — Slow, parametrized sweeps:
- `test_comm_failure_degradation`: parametrize failure_rate=[0.1, 0.3, 0.5], degradation < 30%
- `test_comm_delay_degradation`: parametrize delay_steps=[1, 2, 3], degradation < 30%

### 7.4 Running Tests

```bash
pytest tests/ -v -m "not slow"    # Daily development (seconds)
pytest tests/ -v                   # Full CI run (minutes)
pytest tests/ -k "kundur" -v       # Single scenario
```

## 8. File Migration

### 8.1 Archive (root → tests/archive/)

11 files moved:
- test_eval_diag.py, test_eval_rl.py, test_freq_diag.py
- test_ne_debug.py ~ test_ne_debug5.py
- test_ne_verify.py, test_regca1_debug.py, test_regca1_verify.py

Archive README.md explains these are historical debug files, excluded from pytest.

### 8.2 New Files

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| plotting/configs.py | ~120 | Configuration dataclasses |
| plotting/evaluate.py | ~100 | Evaluation pipeline |
| plotting/generate_all.py | ~80 | Figure orchestration |
| tests/conftest.py | ~60 | Shared fixtures |
| tests/test_env.py | ~30 | Environment tests |
| tests/test_training.py | ~25 | Convergence tests |
| tests/test_eval.py | ~50 | Evaluation tests |
| tests/test_robustness.py | ~50 | Robustness tests |
| pytest.ini | ~5 | pytest config |

Total new code: ~520 lines across 9 files.

## 9. Implementation Notes

### 9.1 Missing `close()` on AndesBaseEnv

`AndesBaseEnv` does not define a `close()` method. Add one during implementation:

```python
# env/andes/base_env.py
def close(self):
    """Clean up ANDES system resources."""
    self.ss = None
```

All fixtures and generate_all.py call `env.close()`. Without this, `AttributeError` at runtime.

### 9.2 REGCA1 Scenario — Deprecated

The `AndesNERegca1Env` environment and `results/andes_ne_regca1_models/` are not covered
by this spec. REGCA1 is deprecated and will not receive a `SCENARIOS` entry or `IO_PRESET`.
Historical test files (`test_regca1_debug.py`, `test_regca1_verify.py`) are archived as-is.

### 9.3 Reward Aggregation in Trajectory

The env returns per-agent rewards as `dict[int, float]`. `Trajectory.rewards` stores the
sum across agents at each step: `rewards[t] = sum(agent_rewards.values())`. This matches
the existing `plot_andes_eval.py` convention where total reward per step is tracked.

## 10. Design Decisions

1. **Three-layer config** (Scenario/Eval/IO) — physical system, evaluation method, and output paths are independent concerns
2. **Typed disturbances** — DisturbanceBase hierarchy catches field mismatches at definition time
3. **evaluate.py produces data only** — both tests and generate_all.py consume EvalResult without coupling
4. **paper_style.py: return fig, remove internal save** — breaking change, but enables reuse by tests and generate_all.py
5. **Module-scoped fixtures throughout** — avoids ScopeMismatch and expensive re-creation of ANDES envs
6. **Slow markers** — daily dev runs in seconds, CI runs full suite
7. **Factory functions defined in evaluate.py** — `create_env` / `load_agents` centralize construction with fixed SAC hyperparams
8. **dataclasses.replace for sweep configs** — preserves caller's base EvalConfig when overriding comm params
