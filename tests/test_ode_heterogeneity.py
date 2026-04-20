"""Parameter heterogeneity helper tests."""
import numpy as np
import pytest

from utils.ode_heterogeneity import generate_heterogeneous_params


def test_zero_spread_returns_uniform():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.0, seed=0)
    np.testing.assert_array_equal(out, base)


def test_mean_preserved_within_tolerance():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert abs(float(out.mean()) - 24.0) < 0.1


def test_spread_produces_distinct_values():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert len(set(out.tolist())) == len(base)
    assert (out > 0).all()


def test_seed_is_deterministic():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    a = generate_heterogeneous_params(base, spread=0.3, seed=42)
    b = generate_heterogeneous_params(base, spread=0.3, seed=42)
    np.testing.assert_array_equal(a, b)


def test_rejects_negative_spread():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    with pytest.raises(ValueError):
        generate_heterogeneous_params(base, spread=-0.1, seed=0)


def test_enforces_positive_floor():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    # seed=4 at spread=0.95 produces a pre-floor element < 0, triggering clamping
    out = generate_heterogeneous_params(base, spread=0.95, seed=4)
    assert (out >= 1e-3).all()
    # Mean is NOT preserved when floor fires — this is expected and documented
    assert abs(float(out.mean()) - 24.0) > 0.1


def test_rejects_spread_ge_one():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    with pytest.raises(ValueError):
        generate_heterogeneous_params(base, spread=1.0, seed=0)


def test_multivsg_env_uses_heterogeneous_H_when_flag_on(monkeypatch):
    """With ODE_HETEROGENEOUS=True, PowerSystem should receive non-uniform H."""
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_H_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    H = env.ps.H_es0
    assert len(set(H.tolist())) > 1, "Expected heterogeneous H, got uniform"


def test_multivsg_env_uses_heterogeneous_D_when_flag_on(monkeypatch):
    """With ODE_HETEROGENEOUS=True, PowerSystem should also receive non-uniform D."""
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_D_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    D = env.ps.D_es0
    assert len(set(D.tolist())) > 1, "Expected heterogeneous D, got uniform"


def test_multivsg_env_action_decode_uses_heterogeneous_base(monkeypatch):
    """After step(), H_es/D_es must be based on _H_base/_D_base, not cfg.H_ES0/D_ES0."""
    import numpy as np
    import config as cfg
    monkeypatch.setattr(cfg, 'ODE_HETEROGENEOUS', True)
    monkeypatch.setattr(cfg, 'ODE_H_SPREAD', 0.30)
    monkeypatch.setattr(cfg, 'ODE_D_SPREAD', 0.30)
    from env.ode.multi_vsg_env import MultiVSGEnv
    env = MultiVSGEnv()
    env.reset(delta_u=np.zeros(env.N))
    # Zero action = no H/D change from base; ps.H_es must equal _H_base (heterogeneous)
    zero_actions = {i: np.zeros(2) for i in range(env.N)}
    env.step(zero_actions)
    assert len(set(env.ps.H_es.tolist())) > 1, \
        "H_es after zero-action step should reflect _H_base, not uniform cfg.H_ES0"
    assert len(set(env.ps.D_es.tolist())) > 1, \
        "D_es after zero-action step should reflect _D_base, not uniform cfg.D_ES0"
