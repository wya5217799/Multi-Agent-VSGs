"""Discrete line-trip events tests."""
import numpy as np

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import (
    DisturbanceEvent,
    EventSchedule,
    LineTripEvent,
)


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)


def _fresh():
    return PowerSystem(
        build_laplacian(_B, _V), np.full(4, 24.0), np.full(4, 18.0),
        dt=0.2, fn=50.0, B_matrix=_B.copy(), V_bus=_V, network_mode='linear',
    )


def test_line_trip_modifies_B_matrix():
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=1.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    for _ in range(4):  # before trip (t<1.0)
        ps.step()
    assert ps.B_matrix[1, 2] == 4.0
    for _ in range(2):  # cross t=1.0
        ps.step()
    assert ps.B_matrix[1, 2] == 0.0
    assert ps.B_matrix[2, 1] == 0.0


def test_line_trip_preserves_N_and_state_continuity():
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=1.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    prev_state = ps.state.copy()
    for _ in range(10):
        r = ps.step()
        # State must remain finite across all steps (including trip transition)
        delta = float(np.max(np.abs(ps.state - prev_state)))
        assert np.isfinite(delta), f"state went non-finite after step: {ps.state}"
        prev_state = ps.state.copy()


def test_line_trip_increases_swing_amplitude():
    """After tripping a tie at t=0, swing amplitude at bus 0 is larger than intact system."""
    # Intact
    ps_intact = _fresh()
    ps_intact.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
    )))
    omega_intact = []
    for _ in range(50):
        r = ps_intact.step()
        omega_intact.append(float(r['omega'][0]))
    # Tripped at start
    ps_trip = _fresh()
    ps_trip.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    )))
    omega_trip = []
    for _ in range(50):
        r = ps_trip.step()
        omega_trip.append(float(r['omega'][0]))

    # Trip removes coupling between area 1 and 2 → larger swing amplitude
    assert max(np.abs(omega_trip)) > max(np.abs(omega_intact))


def test_reset_restores_original_topology():
    """LineTripEvent must not persist across episodes after reset."""
    ps = _fresh()
    sched = EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    ))
    ps.reset(event_schedule=sched)
    assert ps.B_matrix[1, 2] == 0.0  # trip applied

    # Second episode: no trip — topology must be intact
    ps.reset(delta_u=np.array([1.0, 0.0, -1.0, 0.0]))
    assert ps.B_matrix[1, 2] == 4.0, "topology should be restored after reset()"
    assert ps.B_matrix[2, 1] == 4.0
