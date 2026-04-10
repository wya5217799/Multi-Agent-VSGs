"""Shared pytest fixtures for Multi-Agent VSG tests."""
import pytest
import numpy as np

from plotting.configs import SCENARIOS, IO_PRESETS, CommConfig
from plotting.evaluate import create_env, load_agents, _get_zero_action


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
    try:
        _env = create_env(scenario)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    yield _env
    _env.close()


@pytest.fixture(scope="module")
def trained_agents(scenario, io_config):
    """Load trained SAC agents."""
    return load_agents(io_config.model_dir, scenario.n_agents)


@pytest.fixture(scope="module")
def baseline_reward(env, scenario):
    """No-control baseline cumulative reward, run once per module."""
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
