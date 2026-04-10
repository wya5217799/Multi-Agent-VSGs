"""Communication robustness tests — slow, parametrized sweeps."""
import pytest
from plotting.configs import CommConfig
from plotting.evaluate import create_env


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
