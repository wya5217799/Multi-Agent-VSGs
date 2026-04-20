"""Minimal smoke coverage for the stable ANDES Kundur path."""

import importlib.util

import pytest


HAS_ANDES = importlib.util.find_spec("andes") is not None


@pytest.mark.skipif(
    not HAS_ANDES,
    reason="ANDES is optional in this workspace; smoke tests run where it is installed.",
)
@pytest.mark.slow
def test_andes_kundur_reset_and_step_smoke():
    from env.andes.andes_vsg_env import AndesMultiVSGEnv
    from plotting.evaluate import get_zero_action

    env = AndesMultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    try:
        obs = env.reset()
        assert obs is not None
        assert isinstance(obs, dict)
        assert len(obs) == env.N_AGENTS
        assert not env.ss.TDS.busted

        zero_action = get_zero_action(env)
        for _ in range(3):
            actions = {i: zero_action.copy() for i in range(env.N_AGENTS)}
            obs, rewards, done, info = env.step(actions)
            assert isinstance(obs, dict)
            assert isinstance(rewards, dict)
            assert len(rewards) == env.N_AGENTS
            assert not info.get("tds_failed", False)
            assert "freq_hz" in info
            assert "P_es" in info
            if done:
                break
    finally:
        env.close()
