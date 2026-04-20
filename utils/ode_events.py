"""Discrete event primitives for ODE multi-VSG simulation.

Events are applied at the start of each control step. The schedule is
frozen (immutable) so that environments can safely share it across resets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np


@dataclass(frozen=True)
class DisturbanceEvent:
    """Replace the current network-wide Δu vector at time `t` (s)."""
    t: float
    delta_u: np.ndarray  # shape (N,)

    def __post_init__(self) -> None:
        arr = np.asarray(self.delta_u, dtype=np.float64)
        object.__setattr__(self, "delta_u", arr)


@dataclass(frozen=True)
class LineTripEvent:
    """Remove the (i,j) edge from the network Laplacian at time `t`."""
    t: float
    bus_i: int
    bus_j: int


Event = Union[DisturbanceEvent, LineTripEvent]


@dataclass(frozen=True)
class EventSchedule:
    """Sorted, immutable list of events applied in order of `t`."""
    events: tuple[Event, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        times = [e.t for e in self.events]
        if any(t_next < t_prev for t_prev, t_next in zip(times, times[1:])):
            raise ValueError(f"Event times must be non-decreasing, got {times}")
        if any(t < 0 for t in times):
            raise ValueError(f"Event times must be non-negative, got {times}")

    def events_in_window(self, t0: float, t1: float) -> list[Event]:
        """Return events with t0 <= e.t < t1 (half-open, aligns with step start)."""
        return [e for e in self.events if t0 <= e.t < t1]
