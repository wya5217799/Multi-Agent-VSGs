"""Nonlinear swing-equation network mode tests."""
import numpy as np
import pytest

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)
_L = build_laplacian(_B, _V)


def _run(mode, amplitude, steps=25):
    ps = PowerSystem(
        _L, np.full(4, 24.0), np.full(4, 18.0),
        dt=0.2, fn=50.0,
        B_matrix=_B, V_bus=_V, network_mode=mode,
    )
    ps.reset(delta_u=np.array([amplitude, 0.0, -amplitude, 0.0]))
    peak_omega = 0.0
    for _ in range(steps):
        r = ps.step()
        peak_omega = max(peak_omega, float(np.max(np.abs(r['omega']))))
    return peak_omega


def test_linear_mode_default():
    # Default = linear, backward compatible
    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    assert getattr(ps, 'network_mode', 'linear') == 'linear'


def test_small_disturbance_linear_nonlinear_agree():
    # For small theta (amplitude 0.2 p.u.), sin(θ) ≈ θ within 1%
    lin = _run('linear', amplitude=0.2)
    non = _run('nonlinear', amplitude=0.2)
    rel_err = abs(lin - non) / max(abs(lin), 1e-9)
    assert rel_err < 0.02, f"small-signal lin/nonlin diverge: lin={lin}, non={non}"


def test_large_disturbance_linear_nonlinear_diverge():
    # At amplitude ~3 p.u. angles grow large; sin saturates, linear over-predicts
    lin = _run('linear', amplitude=3.0)
    non = _run('nonlinear', amplitude=3.0)
    rel_err = abs(lin - non) / max(abs(lin), 1e-9)
    assert rel_err > 0.02, f"large-signal lin/nonlin should diverge >2%, got {rel_err:.4f}"


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        PowerSystem(
            _L, np.full(4, 24.0), np.full(4, 18.0),
            dt=0.2, fn=50.0,
            B_matrix=_B, V_bus=_V, network_mode='bogus',
        )
