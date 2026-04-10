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
