"""
Unified evaluation pipeline — data only, no plotting.

Produces Trajectory and EvalResult dataclasses consumed by
both tests/ and generate_all.py.
"""
import json
import os
import numpy as np
from dataclasses import dataclass

from plotting.configs import (
    ScenarioConfig, EvalConfig, CommConfig, IOConfig,
    resolve_env_class, DisturbanceBase, LoadStep,
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

    ANDES env constructors don't take case_path/n_agents as params.
    case_path is hardcoded per class, n_agents is a class constant.
    We only pass comm-related params.
    """
    comm = comm or CommConfig()
    try:
        env_cls = resolve_env_class(scenario.env_type)
    except Exception as exc:
        raise RuntimeError(
            f"Backend for scenario '{scenario.name}' is unavailable: {exc}"
        ) from exc
    return env_cls(
        random_disturbance=True,
        comm_fail_prob=comm.failure_rate,
        comm_delay_steps=comm.delay_steps,
    )


def load_agents(model_dir: str, n_agents: int) -> list:
    """Load trained SAC agents from checkpoint directory.

    Kundur (4 agents) uses hidden_sizes=[128,128,128,128].
    NE (8 agents) uses hidden_sizes=[256,256].
    """
    hidden = [128, 128, 128, 128]
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


# ── Episode runner helpers ──

def _build_delta_u(disturbance: DisturbanceBase) -> dict:
    """Convert typed DisturbanceBase to env.reset(delta_u=...) format.

    Maps disturbance name to PQ index following plot_andes_eval.py convention:
      LS1 -> PQ_0 (load increase), LS2 -> PQ_1 (load decrease)
    """
    if isinstance(disturbance, LoadStep):
        pq_map = {"LS1": "PQ_0", "LS2": "PQ_1"}
        pq_key = pq_map.get(disturbance.name, "PQ_0")
        return {pq_key: -disturbance.delta_p}
    return {}


def _get_zero_action(env) -> np.ndarray:
    """Compute the normalized action for DeltaM=0, DeltaD=0."""
    a0 = (0 - env.DM_MIN) / (env.DM_MAX - env.DM_MIN) * 2 - 1
    a1 = (0 - env.DD_MIN) / (env.DD_MAX - env.DD_MIN) * 2 - 1
    return np.array([a0, a1], dtype=np.float32)


# ── Core evaluation ──

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
    Creates new envs per comm config since comm params are set at construction.
    """
    from dataclasses import replace
    results = {}

    for rate in (failure_rates or []):
        cfg = replace(eval_cfg, comm=CommConfig(failure_rate=rate))
        sweep_env = create_env(scenario, cfg.comm)
        results[f"fail_{rate}"] = run_evaluation(
            scenario, disturbance, cfg, method="rl",
            env=sweep_env, agents=agents,
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
