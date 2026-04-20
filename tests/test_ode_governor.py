"""Governor / droop dynamics tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_L = build_laplacian(_B, np.ones(4))


def test_governor_off_is_default():
    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    assert getattr(ps, 'governor_enabled', False) is False
    assert ps.state.shape == (8,)  # 2N = 8


def test_governor_on_extends_state():
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    assert ps.state.shape == (12,)  # 3N = 12


def test_governor_steady_state_droop():
    """Unbalanced step -> after long simulation P_gov ≈ -(ω/ω_s)/R at each bus."""
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    # Unbalanced load step (CoI shifts)
    ps.reset(delta_u=np.array([-1.0, -1.0, -1.0, -1.0]))
    for _ in range(300):  # 60 s to converge
        r = ps.step()
    omega = r['omega']
    P_gov = ps.state[2 * 4:3 * 4]
    # Steady-state governor relation: P_gov ≈ -(ω/ωs) / R  (ω in rad/s, R in p.u.)
    expected = -(omega / ps.omega_s) / 0.05
    np.testing.assert_allclose(P_gov, expected, rtol=0.10)


def test_governor_reduces_frequency_deviation():
    """With governor, steady-state |Δω| is smaller than without for unbalanced step."""
    delta_u = np.array([-1.0, -1.0, -1.0, -1.0])
    # Without governor
    ps_off = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    ps_off.reset(delta_u=delta_u)
    for _ in range(300):
        r_off = ps_off.step()
    # With governor
    ps_on = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
        governor_enabled=True, governor_R=0.05, governor_tau_g=0.5,
    )
    ps_on.reset(delta_u=delta_u)
    for _ in range(300):
        r_on = ps_on.step()
    ss_off = float(np.mean(np.abs(r_off['omega'])))
    ss_on = float(np.mean(np.abs(r_on['omega'])))
    assert ss_on < 0.5 * ss_off, f"governor should cut SS |ω|: off={ss_off}, on={ss_on}"


def test_invalid_governor_params_rejected():
    import pytest
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
            governor_enabled=True, governor_R=0.0, governor_tau_g=0.5,
        )
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
            governor_enabled=True, governor_R=0.05, governor_tau_g=0.0,
        )
