"""Control effectiveness tests — slow, requires model loading."""
import pytest


@pytest.mark.slow
def test_rl_beats_baseline(env, scenario, trained_agents, baseline_reward):
    """RL control cumulative reward significantly exceeds no-control baseline."""
    obs = env.reset()
    total = 0.0
    for _ in range(env.STEPS_PER_EPISODE):
        actions = {i: trained_agents[i].select_action(obs[i], deterministic=True)
                   for i in range(scenario.n_agents)}
        obs, rewards, done, _ = env.step(actions)
        total += sum(rewards.values()) if isinstance(rewards, dict) else float(rewards)
        if done:
            break
    # For negative rewards (penalty-based), less negative = better.
    assert total > baseline_reward, (
        f"RL reward {total:.2f} not better than baseline {baseline_reward:.2f}"
    )
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
