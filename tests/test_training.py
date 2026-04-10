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
