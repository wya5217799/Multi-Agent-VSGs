"""Intra-episode disturbance scheduling tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import DisturbanceEvent, EventSchedule


def _make_ps():
    B = np.array([
        [0, 4, 0, 0],
        [4, 0, 4, 0],
        [0, 4, 0, 4],
        [0, 0, 4, 0],
    ], dtype=float)
    L = build_laplacian(B, np.ones(4))
    return PowerSystem(L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)


def test_empty_schedule_matches_static_disturbance():
    # Baseline: static delta_u set at reset
    ps_static = _make_ps()
    ps_static.reset(delta_u=np.array([2.0, 0.0, -2.0, 0.0]))
    for _ in range(25):
        ps_static.step()
    theta_static = ps_static.state[:4].copy()

    # New path: same disturbance via EventSchedule at t=0
    ps_sched = _make_ps()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([2.0, 0.0, -2.0, 0.0])),
    ))
    ps_sched.reset(event_schedule=sched)
    for _ in range(25):
        ps_sched.step()
    theta_sched = ps_sched.state[:4].copy()

    np.testing.assert_allclose(theta_static, theta_sched, atol=1e-9)


def test_mid_episode_event_changes_trajectory():
    ps = _make_ps()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([2.0, 0.0, -2.0, 0.0])),
        DisturbanceEvent(t=2.0, delta_u=np.array([0.0, 0.0, 0.0, 0.0])),  # load restored
    ))
    ps.reset(event_schedule=sched)
    pre_peak = 0.0
    post_peak = 0.0
    for step in range(50):  # 10s
        r = ps.step()
        omega_mag = float(np.max(np.abs(r['omega'])))
        if step < 10:
            pre_peak = max(pre_peak, omega_mag)
        else:
            post_peak = max(post_peak, omega_mag)
    # After disturbance is removed at t=2s, oscillation decays
    assert post_peak < pre_peak


def test_schedule_rejects_non_monotonic_times():
    import pytest
    with pytest.raises(ValueError):
        EventSchedule(events=(
            DisturbanceEvent(t=2.0, delta_u=np.zeros(4)),
            DisturbanceEvent(t=1.0, delta_u=np.zeros(4)),
        ))
